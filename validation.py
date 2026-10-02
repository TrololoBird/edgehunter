"""
One place for the statistics every result has to pass (ML_PLAN.md, phase A):

- `block_stats` / `bh`: block-bootstrap interval and p of a mean, Benjamini-Hochberg q-values (moved here from
  research_edges.py, which re-exports them);
- `cpcv_splits`: combinatorial purged cross-validation (López de Prado, AFML ch. 12): the timeline in N groups, every
  choice of k test groups is one split; training rows whose label window [t0, t1] overlaps a test group are purged,
  and an embargo after each test group is dropped too;
- `deflated_sharpe`: the probability that the true Sharpe ratio is above the best one expected from `n_trials`
  unskilled trials (Bailey & López de Prado 2014), with the skew / kurtosis of the returns;
- `pbo`: the probability of backtest overfitting by CSCV (Bailey, Borwein, López de Prado, Zhu 2017): how often the
  variant best in-sample ranks below the median out-of-sample;
- `trials`: the registry of every variant tried (research/trials.csv): the n_trials of the deflated Sharpe.
"""
import csv
import itertools
import math
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

BOOT = 2000
EULER = 0.5772156649015329
TRIALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'research', 'trials.csv')
TRIAL_FIELDS = ['date', 'script', 'name', 'variants', 'params', 'window', 'n', 'metric', 'dev', 'valid', 'holdout',
                'source', 'commit']


# ---------------------------------------------------------------------------------------------- bootstrap / FDR

def block_stats(values: np.ndarray, blocks: np.ndarray, seed: int = 7) -> Tuple[float, float, float, float, int]:
    """(mean, lo, hi, two-sided p, number of blocks): 90% interval and p of the mean from a block bootstrap."""
    order = np.argsort(blocks, kind='stable')
    v, b = values[order], blocks[order]
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    sums = np.add.reduceat(v, starts)
    counts = np.diff(np.r_[starts, len(v)])
    k = len(sums)
    if k < 5:
        return float(values.mean()) if len(values) else float('nan'), float('nan'), float('nan'), float('nan'), k
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, k, size=(BOOT, k))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.quantile(means, [0.05, 0.95])
    below = float((means <= 0).mean())
    p = min(1.0, 2 * min(below, 1 - below) + 1 / BOOT)
    return float(values.mean()), float(lo), float(hi), p, k


def bh(pvalues: List[float]) -> List[float]:
    """Benjamini-Hochberg q-values (NaN stays NaN)."""
    idx = sorted((p, i) for i, p in enumerate(pvalues) if not math.isnan(p))
    q = [float('nan')] * len(pvalues)
    running, m = 1.0, len(idx)
    for rank in range(m, 0, -1):
        p, i = idx[rank - 1]
        running = min(running, p * m / rank)
        q[i] = running
    return q


# ---------------------------------------------------------------------------------------------- CPCV

def cpcv_splits(t0: np.ndarray, t1: np.ndarray, n_groups: int = 6, k_test: int = 2,
                embargo: float = 0.01) -> Iterator[Tuple[np.ndarray, np.ndarray, Tuple[int, ...]]]:
    """
    Yields (train index, test index, test groups) for every combination of k_test of n_groups contiguous time
    groups. t0 / t1 = each row's label start / end (same unit). Purging: a training row whose [t0, t1] overlaps a
    test group's [min t0, max t1] is dropped; embargo: rows starting within `embargo` x the whole span after a test
    group's end are dropped as well. Rows must be sorted by t0.
    """
    n = len(t0)
    if n == 0:
        return
    bounds = np.linspace(0, n, n_groups + 1).astype(int)
    groups = [np.arange(bounds[g], bounds[g + 1]) for g in range(n_groups)]
    span = float(t1.max() - t0.min()) or 1.0
    for test_groups in itertools.combinations(range(n_groups), k_test):
        test = np.concatenate([groups[g] for g in test_groups])
        keep = np.ones(n, dtype=bool)
        keep[test] = False
        for g in test_groups:
            lo, hi = t0[groups[g]].min(), t1[groups[g]].max()
            keep &= ~((t0 <= hi) & (t1 >= lo))                         # purge overlapping labels
            keep &= ~((t0 > hi) & (t0 <= hi + embargo * span))         # embargo after the test group
        yield np.flatnonzero(keep), test, test_groups


def cpcv_paths(n_groups: int, k_test: int) -> int:
    """The number of backtest paths CPCV yields: C(N, k) x k / N."""
    return math.comb(n_groups, k_test) * k_test // n_groups


# ---------------------------------------------------------------------------------------------- deflated Sharpe

def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    """Inverse standard normal (Acklam's rational approximation, |error| < 1.2e-9)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if p <= 0 or p >= 1:
        return float('inf') if p >= 1 else float('-inf')
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - lo:
        return -_norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def expected_max_sharpe(n_trials: int, var_sharpe: float) -> float:
    """E[max SR] of n_trials unskilled strategies whose Sharpe ratios have variance var_sharpe (per-period units)."""
    if n_trials <= 1:
        return 0.0
    s = math.sqrt(max(var_sharpe, 0.0))
    return s * ((1 - EULER) * _norm_ppf(1 - 1 / n_trials) + EULER * _norm_ppf(1 - 1 / (n_trials * math.e)))


def probabilistic_sharpe(returns: Sequence[float], benchmark_sr: float = 0.0) -> float:
    """PSR: P(true per-period SR > benchmark_sr) given the sample's length, skew and kurtosis."""
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = len(r)
    if n < 3 or r.std(ddof=1) == 0:
        return float('nan')
    sr = r.mean() / r.std(ddof=1)
    z = (r - r.mean()) / r.std(ddof=0)
    skew, kurt = float((z ** 3).mean()), float((z ** 4).mean())
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if denom <= 0:
        return float('nan')
    return _norm_cdf((sr - benchmark_sr) * math.sqrt(n - 1) / math.sqrt(denom))


def deflated_sharpe(returns: Sequence[float], n_trials: int, var_sharpe: Optional[float] = None) -> float:
    """
    DSR = PSR against the Sharpe ratio expected as the best of n_trials unskilled trials. var_sharpe = the variance
    of the trials' per-period Sharpe ratios; without it the sampling variance 1 / (n - 1) of a zero-SR estimate.
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 3:
        return float('nan')
    v = var_sharpe if var_sharpe is not None else 1.0 / (len(r) - 1)
    return probabilistic_sharpe(r, expected_max_sharpe(n_trials, v))


# ---------------------------------------------------------------------------------------------- PBO

def pbo(perf: np.ndarray, n_splits: int = 16) -> Tuple[float, np.ndarray]:
    """
    CSCV: perf = (time periods x variants) matrix of per-period performance (e.g. mean R per block). The periods
    are cut into n_splits (even) groups; for each half / half combination the variant best in-sample is ranked
    out-of-sample. Returns (PBO = share of combinations whose logit <= 0, the logits).
    """
    perf = np.asarray(perf, dtype=float)
    t, m = perf.shape
    if m < 2 or t < n_splits:
        return float('nan'), np.empty(0)
    n_splits -= n_splits % 2
    chunks = np.array_split(np.arange(t), n_splits)
    logits = []
    for ins in itertools.combinations(range(n_splits), n_splits // 2):
        is_idx = np.concatenate([chunks[i] for i in ins])
        oos_idx = np.concatenate([chunks[i] for i in range(n_splits) if i not in ins])
        is_perf = np.nanmean(perf[is_idx], axis=0)
        oos_perf = np.nanmean(perf[oos_idx], axis=0)
        best = int(np.nanargmax(is_perf))
        ties = np.sum(np.isclose(oos_perf, oos_perf[best], rtol=0.0, atol=1e-15)) - 1
        rank = (np.sum(oos_perf < oos_perf[best]) + 0.5 * ties) / (m - 1)
        w = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(w / (1 - w)))
    logits = np.asarray(logits)
    return float((logits <= 0).mean()), logits


# ---------------------------------------------------------------------------------------------- trial registry

def _commit() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True,
                              cwd=os.path.dirname(TRIALS_PATH), timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def record_trial(script: str, name: str, params: str = '', window: str = '', n: int = 0, metric: str = 'R',
                 dev: Optional[float] = None, valid: Optional[float] = None, holdout: Optional[float] = None,
                 variants: int = 1, source: str = ''):
    """Appends one tried variant (or a grid of `variants`) to research/trials.csv: the n_trials of the DSR."""
    new = not os.path.exists(TRIALS_PATH)
    os.makedirs(os.path.dirname(TRIALS_PATH), exist_ok=True)
    fmt = lambda v: '' if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.6g}"  # noqa: E731
    with open(TRIALS_PATH, 'a', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(TRIAL_FIELDS)
        w.writerow([datetime.now(timezone.utc).date().isoformat(), script, name, variants, params, window, n, metric,
                    fmt(dev), fmt(valid), fmt(holdout), source, _commit()])


def trials(script: Optional[str] = None) -> List[Dict[str, str]]:
    if not os.path.exists(TRIALS_PATH):
        return []
    with open(TRIALS_PATH, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    return [r for r in rows if script is None or r['script'] == script]


def n_trials() -> int:
    """Every variant ever tried (with the back-filled history): the honest multiple-testing count."""
    return max(1, sum(int(r.get('variants') or 1) for r in trials()))
