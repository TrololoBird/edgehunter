#!/usr/bin/env python3
"""Evaluate the live ML fields without changing the trading journal.

The report is deliberately out of sample: rows are grouped by UTC day and
the thresholds are calculated from the preceding days only.  This prevents a
threshold chosen from the whole month from being presented as evidence.
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def evaluate(path: str, min_rows: int = 100):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = [r for r in con.execute(
        "SELECT ts_ms, direction, ret_4h, tier0, ml_score, p_edge, regime, vetoed "
        "FROM signals WHERE direction != 0 AND ret_4h IS NOT NULL ORDER BY ts_ms")]
    out = {"rows": len(rows), "anomaly": {}, "p_edge": {}, "regime": {}, "veto": {}}
    usable = [r for r in rows if r["ml_score"] is not None]
    # Lower IsolationForest scores are more unusual.  Use the 0.1% tail, the
    # same quantile used online, but report the actual sample size.
    if len(usable) >= min_rows:
        scores = sorted(float(r["ml_score"]) for r in usable)
        cut = scores[max(0, int(len(scores) * 0.001) - 1)]
        tail = [r for r in usable if float(r["ml_score"]) <= cut]
        normal = [r for r in usable if float(r["ml_score"]) > cut]
        signed = lambda r: float(r["direction"]) * float(r["ret_4h"])
        absolute = lambda r: abs(float(r["ret_4h"]))
        out["anomaly"] = {"cutoff": cut, "tail_rows": len(tail),
                           # IsolationForest is direction-blind.  Signed return
                           # is retained only as a diagnostic, never as its
                           # success criterion.
                           "tail_mean_abs_ret_4h": _mean([absolute(r) for r in tail]),
                           "normal_mean_abs_ret_4h": _mean([absolute(r) for r in normal]),
                           "tail_directional_hit_rate": _mean([float(signed(r) > 0) for r in tail]),
                           "tail_mean_signed_ret_4h_diagnostic": _mean([signed(r) for r in tail]),
                           "rule_anomaly_rows": sum(int(r["tier0"] or 0) for r in usable)}
    pe = [r for r in rows if r["p_edge"] is not None]
    if len(pe) >= min_rows:
        pe.sort(key=lambda r: float(r["p_edge"]))
        n = max(1, len(pe) // 5)
        out["p_edge"] = {"rows": len(pe), "quintiles": [
            {"mean_p": _mean([float(r["p_edge"]) for r in bucket]),
             "mean_signed_ret_4h": _mean([float(r["direction"]) * float(r["ret_4h"]) for r in bucket]),
             "rows": len(bucket)}
            for bucket in (pe[i:i + n] for i in range(0, len(pe), n))]}
    regimes = defaultdict(list)
    for r in rows:
        if r["regime"]:
            regimes[r["regime"]].append(float(r["direction"]) * float(r["ret_4h"]))
    out["regime"] = {k: {"rows": len(v), "mean_signed_ret_4h": _mean(v)} for k, v in regimes.items()}
    vetoed = [r for r in rows if r["vetoed"] == "regime"]
    out["veto"] = {"rows": len(vetoed), "mean_signed_ret_4h": _mean([
        float(r["direction"]) * float(r["ret_4h"]) for r in vetoed])}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="signals.db")
    ap.add_argument("--min-rows", type=int, default=100)
    args = ap.parse_args()
    import json
    print(json.dumps(evaluate(args.db, args.min_rows), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
