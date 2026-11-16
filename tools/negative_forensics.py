#!/usr/bin/env python3
"""Build a veto-aware negative-entry and demo-execution report.

The report deliberately keeps executable replay rows separate from shadow
benchmarks.  It is a small sqlite-only utility so it can run against the live
databases without importing the event loop or exchange client.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
import re
import sqlite3
import sys
from pathlib import Path


DEFAULT_CUTOFF_MS = 1794623715000
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
try:
    from config import CONFIG
    DEFAULT_LOGIC_VERSION = CONFIG.journal.logic_version
except Exception:  # pragma: no cover - the report can still run against a copied sqlite file
    DEFAULT_LOGIC_VERSION = None


BENCHMARK_REASONS = frozenset({
    'flow_entry', 'reclaim_entry', 'weak_mss', 'variant_ce_limit', 'variant_fvg_edge',
    'variant_pool2', 'variant_retest', 'variant_shift', 'variant_st_stop', 'variant_orb_open',
})


def read_rows(path: str, table: str, where: str = "", args: tuple = ()):
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY ts_ms" if table == "signals" else " ORDER BY opened_ms"
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def val(row, key, default=None):
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def setup(row) -> str:
    return str(val(row, 'group_key', '') or '').removeprefix('ENTRY ')


def is_setup(row, name: str) -> bool:
    raw = str(val(row, 'group_key', '') or '')
    return setup(row) == name or raw.endswith(' ' + name)


def truthy(row, key) -> bool:
    return bool(val(row, key, 0) or 0)


def is_benchmark_variant(row) -> bool:
    if truthy(row, 'is_benchmark_variant'):
        return True
    reason = str(val(row, 'vetoed') or '')
    return reason in BENCHMARK_REASONS or reason.startswith('variant_')


def pct(n, d) -> str:
    return f"{100 * n / d:.1f}%" if d else '—'


def fmt(value, digits=2) -> str:
    if value is None:
        return '—'
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{value:.{digits}f}" if math.isfinite(value) else '—'


def median(values):
    values = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def top(rows, field: str) -> str:
    counts = collections.Counter(str(val(row, field) or 'NULL') for row in rows)
    return counts.most_common(1)[0][0] if counts else '—'


def table_header(columns) -> str:
    return '| ' + ' | '.join(columns) + ' |\n|' + '|'.join('---' for _ in columns) + '|'


def in_scope(row, logic_version=None, source_commit=None) -> bool:
    """Apply the provenance slice without assuming either field is populated."""
    if logic_version is not None and val(row, 'logic_version') != logic_version:
        return False
    if source_commit is not None and val(row, 'source_commit') != source_commit:
        return False
    return True


def market_regime(row) -> str:
    try:
        btc = float(val(row, 'btc_1d'))
        market = float(val(row, 'mkt_1d'))
    except (TypeError, ValueError):
        return 'missing'
    if btc > 0 and market > 0:
        return 'both positive'
    if btc < 0 and market < 0:
        return 'both negative'
    return 'mixed/zero'


def stop_pierce_quantiles(row):
    """Parse the stored p50/p80/p90 buffer percentages, if present.

    ``stop_pierce`` is a measured stop-buffer diagnostic (percentage of the
    stop price), not a realized post-stop excursion in ATR.  Keeping that
    distinction in the report prevents it being read as a causal price path.
    """
    text = str(val(row, 'stop_pierce') or '')
    match = re.search(r'\s([0-9.]+)/([0-9.]+)/([0-9.]+)$', text)
    if not match:
        return None
    return tuple(float(match.group(i)) for i in (1, 2, 3))


def flow_confirmed(row) -> bool:
    try:
        return json.loads(val(row, 'confirms') or '{}').get('flow') is True
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--signals', default='/opt/edgehunter/signals.db')
    ap.add_argument('--demo', default='/opt/edgehunter/demo_trades.db')
    ap.add_argument('--cutoff-ms', type=int, default=DEFAULT_CUTOFF_MS)
    ap.add_argument('--logic-version', default=DEFAULT_LOGIC_VERSION,
                    help='restrict both databases to one logic_version (for example eng-170c)')
    ap.add_argument('--source-commit', default=None,
                    help='restrict both databases to one recorded source_commit')
    ap.add_argument('--out', default='/root/edgehunter_negative_forensics_2026-11-16.md')
    args = ap.parse_args()

    signals_all = read_rows(args.signals, 'signals', 'ts_ms >= ?', (args.cutoff_ms,))
    signals = [r for r in signals_all if in_scope(r, args.logic_version, args.source_commit)]
    entries = [r for r in signals if val(r, 'kind') == 'entry']
    valid = [r for r in entries if not truthy(r, 'quarantined')]
    primary = [r for r in valid if not is_benchmark_variant(r)]
    benchmark = [r for r in valid if is_benchmark_variant(r)]
    quarantined = [r for r in entries if truthy(r, 'quarantined')]
    negatives = [r for r in entries if val(r, 'filled') == 1 and val(r, 'r_tp1') is not None and float(val(r, 'r_tp1')) < 0]
    valid_neg = [r for r in negatives if not truthy(r, 'quarantined') and not is_benchmark_variant(r)]
    benchmark_neg = [r for r in negatives if not truthy(r, 'quarantined') and is_benchmark_variant(r)]
    unvetoed_neg = [r for r in valid_neg if val(r, 'vetoed') in (None, '')]
    blocked_neg = [r for r in valid_neg if val(r, 'vetoed') not in (None, '')]
    q_neg = [r for r in negatives if truthy(r, 'quarantined')]
    cards_all = [r for r in signals if val(r, 'kind') == 'card']
    cards = [r for r in cards_all if val(r, 'card_r') is not None]
    neg_cards = [r for r in cards if float(val(r, 'card_r')) < 0]

    demo_all = read_rows(args.demo, 'demo_trades')
    demo = [r for r in demo_all if in_scope(r, args.logic_version, args.source_commit)]
    demo_after = [r for r in demo if (val(r, 'opened_ms') or 0) >= args.cutoff_ms]
    realized_neg = [r for r in demo if val(r, 'r') is not None and float(val(r, 'r')) < 0]
    current_neg = realized_neg
    strategy_after = [r for r in demo_after if val(r, 'setup') not in ('UNTRACKED',) and val(r, 'close_reason') != 'OVERLAP']
    strategy_neg_after = [r for r in strategy_after if val(r, 'r') is not None and float(val(r, 'r')) < 0]
    orphan_neg = [r for r in realized_neg if val(r, 'close_reason') in ('ORPHAN', 'UNTRACKED')]

    groups = collections.defaultdict(list)
    for row in primary:
        groups[setup(row)].append(row)
    neg_groups = collections.defaultdict(list)
    for row in valid_neg:
        neg_groups[setup(row)].append(row)
    unvetoed_groups = collections.defaultdict(list)
    blocked_groups = collections.defaultdict(list)
    for row in unvetoed_neg:
        unvetoed_groups[setup(row)].append(row)
    for row in blocked_neg:
        blocked_groups[setup(row)].append(row)

    lines = []
    now = dt.datetime.now(dt.timezone.utc)
    cut = dt.datetime.fromtimestamp(args.cutoff_ms / 1000, dt.timezone.utc)
    lines += [
        '# Edgehunter: veto-aware negative-entry and execution forensics', '',
        f'Generated `{now.isoformat()}` UTC. Scope starts `{cut.isoformat()}` UTC.',
        f"Provenance filter: logic_version={args.logic_version or 'all'}, source_commit={args.source_commit or 'all'}.", '',
        'The report treats `COALESCE(quarantined, 0) = 0 AND vetoed IS NULL AND is_benchmark_variant = 0` as the executable replay population. '
        'Benchmark rows are identified by `is_benchmark_variant=1` (with legacy reason fallback) and are shown separately; non-benchmark `vetoed` rows are real blocked primary candidates.', '',
        '## Scope counts', '',
        f'- Entry rows: **{len(entries)}**; valid: **{len(valid)}**; primary: **{len(primary)}**; benchmark variants: **{len(benchmark)}**; quarantined: **{len(quarantined)}**.',
        f'- Negative replay rows: **{len(negatives)}**; valid: **{len(valid_neg)}**; '
        f'unvetoed primary: **{len(unvetoed_neg)}**; blocked primary: **{len(blocked_neg)}**; benchmark negatives: **{len(benchmark_neg)}**; quarantined negatives: **{len(q_neg)}**.',
        f'- Cards: **{len(cards_all)}**; cards with result: **{len(cards)}**; negative cards: **{len(neg_cards)}**.',
        f'- Demo rows after cutoff: **{len(demo_after)}**; strategy rows: **{len(strategy_after)}**; '
        f'new negative strategy closes: **{len(strategy_neg_after)}**.',
        '',
        '## All setups: executable vs blocked negatives', '',
        table_header(['Setup', 'Valid entries', 'Valid negative', 'Unvetoed negative', 'Blocked negative', 'Unvetoed share', 'Negative cards']),
    ]
    for name in sorted(groups, key=lambda n: (-len(neg_groups[n]), n)):
        rows = groups[name]
        ncard = sum(1 for r in neg_cards if setup(r) == name or str(val(r, 'group_key', '')).endswith(' ' + name))
        lines.append(f"| {name} | {len(rows)} | {len(neg_groups[name])} | {len(unvetoed_groups[name])} | "
                     f"{len(blocked_groups[name])} | {pct(len(unvetoed_groups[name]), len(neg_groups[name]))} | {ncard} |")

    lines += ['', '## Unvetoed Replay (Passed Filters)', '',
               'These rows are the real leak population: a card could be formed because no veto was recorded.', '',
               table_header(['Setup', 'N', 'Median TP1 R:R', 'MFE ≥0.5R', 'MFE ≥1R', 'Post-stop MFE ≥1R', 'Avg MFE', 'Stop source', 'Zone source']),]
    for name in sorted(unvetoed_groups, key=lambda n: (-len(unvetoed_groups[n]), n)):
        rows = unvetoed_groups[name]
        mfe = [val(r, 'mfe_r') for r in rows if val(r, 'mfe_r') is not None]
        post = [val(r, 'post_stop_mfe_r') for r in rows if val(r, 'post_stop_mfe_r') is not None]
        rr = [val(r, 'rr_tp1') for r in rows if val(r, 'rr_tp1') is not None]
        lines.append(f"| {name} | {len(rows)} | {fmt(median(rr))} | {pct(sum(float(v) >= .5 for v in mfe), len(mfe))} | "
                     f"{pct(sum(float(v) >= 1 for v in mfe), len(mfe))} | {pct(sum(float(v) >= 1 for v in post), len(post))} | "
                     f"{fmt(sum(map(float, mfe)) / len(mfe) if mfe else None)} | {top(rows, 'sl_src')} | {top(rows, 'zone_src')} |")

    lines += ['', '### Unvetoed geometry and causes', '',
               table_header(['Setup', 'N', 'rr_reason', 'low_rr', 'geometry_error', 'risk_gate_reason', 'outcome']),]
    for name in sorted(unvetoed_groups, key=lambda n: (-len(unvetoed_groups[n]), n)):
        rows = unvetoed_groups[name]
        outcomes = collections.Counter(str(val(r, 'outcome') or 'NULL') for r in rows)
        lines.append(f"| {name} | {len(rows)} | {top(rows, 'rr_reason')} | {sum(truthy(r, 'low_rr') for r in rows)} | "
                     f"{top(rows, 'geometry_error')} | {top(rows, 'risk_gate_reason')} | "
                     f"{', '.join(f'{k}={v}' for k, v in outcomes.most_common(4))} |")

    lines += ['', '## Veto Effectiveness (Primary Blocked)', '',
               'These losses are useful for measuring filter coverage, but they do not represent candidates that reached a card.', '',
               table_header(['Veto reason', 'Rows', 'Filled replay', 'Negative', 'Negative among filled', 'Non-negative filled', 'Setups']),]
    blocked_all = [r for r in primary if val(r, 'vetoed') not in (None, '')]
    veto_groups = collections.defaultdict(list)
    for row in blocked_all:
        for reason in str(val(row, 'vetoed')).split(','):
            veto_groups[reason].append(row)
    for reason, rows in sorted(veto_groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        filled_rows = [r for r in rows if val(r, 'filled') == 1 and val(r, 'r_tp1') is not None]
        neg_rows = [r for r in filled_rows if float(val(r, 'r_tp1')) < 0]
        non_negative = len(filled_rows) - len(neg_rows)
        setups = collections.Counter(setup(r) for r in neg_rows)
        lines.append(f"| {reason} | {len(rows)} | {len(filled_rows)} | {len(neg_rows)} | "
                     f"{pct(len(neg_rows), len(filled_rows))} | {non_negative} | "
                     f"{', '.join(f'{k}={v}' for k, v in setups.most_common(8)) or '—'} |")

    lines += ['', '## Quarantined contract rows', '',
               table_header(['Quarantine reason', 'Rows', 'Negative replay', 'Setups']),]
    qgroups = collections.defaultdict(list)
    for row in quarantined:
        qgroups[str(val(row, 'quarantine_reason') or 'NULL')].append(row)
    for reason, rows in sorted(qgroups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines.append(f"| {reason} | {len(rows)} | {sum(r in q_neg for r in rows)} | "
                     f"{', '.join(f'{k}={v}' for k, v in collections.Counter(setup(r) for r in rows).most_common(8))} |")

    lines += ['', '## Realized demo negatives', '',
               f'- All rows in this provenance slice: **{len(realized_neg)}** negative rows; ORPHAN/UNTRACKED: **{len(orphan_neg)}** (excluded from strategy expectancy).',
               f'- Negative rows in the selected logic slice: **{len(current_neg)}**; post-cutoff strategy negatives: **{len(strategy_neg_after)}**.', '',
               table_header(['ID', 'Symbol', 'Setup', 'R', 'Close reason', 'Geometry error', 'Risk gate', 'Stop', 'TP1', 'Entry fill']),]
    for row in current_neg:
        lines.append(f"| {val(row, 'id')} | {val(row, 'symbol')} | {val(row, 'setup')} | {fmt(val(row, 'r'))} | "
                     f"{val(row, 'close_reason') or '—'} | {val(row, 'geometry_error') or '—'} | {val(row, 'risk_gate_reason') or '—'} | "
                     f"{fmt(val(row, 'sl'))} | {fmt(val(row, 'tp1'))} | {fmt(val(row, 'entry_fill'))} |")

    oi_entries = [r for r in primary if is_setup(r, 'OI BUILD SHORT')]
    oi_unveto_neg = [r for r in oi_entries if val(r, 'filled') == 1 and val(r, 'r_tp1') is not None
                     and float(val(r, 'r_tp1')) < 0 and not truthy(r, 'quarantined')
                     and val(r, 'vetoed') in (None, '')]
    oi_cards = [r for r in cards if is_setup(r, 'OI BUILD SHORT')]

    def regime_line(label, rows):
        counts = collections.Counter(market_regime(r) for r in rows)
        negative = (len(rows) if label.startswith('Unvetoed') else
                    sum(float(val(r, 'card_r')) < 0 for r in rows if val(r, 'card_r') is not None))
        return (f"| {label} | {len(rows)} | {counts['both positive']} | {counts['both negative']} | "
                f"{counts['mixed/zero']} | {counts['missing']} | {negative} |")

    lines += [
        '', '## OI BUILD SHORT market_up retrospective', '',
        '`market_up` is a blocking veto: it fires only when both `btc_1d` and `mkt_1d` are strictly positive. '
        'Negative or mixed regimes remain eligible for this particular veto.', '',
        table_header(['Population', 'N', 'Both positive', 'Both negative', 'Mixed/zero', 'Missing', 'Negative']),
        regime_line('Unvetoed negative replay', oi_unveto_neg),
        regime_line('OI BUILD SHORT cards with result', oi_cards),
    ]
    market_up_count = sum(market_regime(r) == 'both positive' for r in oi_unveto_neg)
    flow_false_count = sum(not flow_confirmed(r) for r in oi_unveto_neg)
    combined_count = sum(market_regime(r) == 'both positive' or not flow_confirmed(r) for r in oi_unveto_neg)
    lines.append(f"On this unvetoed-negative slice, `market_up` alone would veto {market_up_count}/{len(oi_unveto_neg)} rows; "
                 f"the new `flow_entry` gate would veto {flow_false_count}/{len(oi_unveto_neg)}; "
                 f"their union would veto {combined_count}/{len(oi_unveto_neg)}.")
    pierce = [stop_pierce_quantiles(r) for r in oi_unveto_neg]
    pierce = [q for q in pierce if q is not None]
    if pierce:
        medians = [median([q[i] for q in pierce]) for i in range(3)]
        kinds = collections.Counter(str(val(r, 'stop_pierce')).split(' ', 1)[0]
                                    for r in oi_unveto_neg if val(r, 'stop_pierce'))
        lines.append('')
        lines.append('`stop_pierce` is stored as measured p50/p80/p90 buffer percentages of the stop price; '
                     'it is not a realized ATR overshoot after the stop.')
        lines.append(f"For the {len(pierce)} unvetoed negative rows, median buffers are "
                     f"p50={medians[0]:.3f}%, p80={medians[1]:.3f}%, p90={medians[2]:.3f}%; "
                     f"stop kinds: {', '.join(f'{k}={v}' for k, v in kinds.most_common())}.")

    lines += ['', '## Conclusions', '',
               f'- The real replay leak is **{len(unvetoed_neg)}** unvetoed negatives, not all **{len(valid_neg)}** valid negatives.',
               f'- Blocked rows account for **{len(blocked_neg)}** valid negatives and are reported as veto effectiveness.',
               '- Any `wrong_stop_side`, `wrong_tp1_side`, or post-fill `low_rr` is a contract failure and belongs in the execution quarantine, not strategy expectancy.',
               '- ORPHAN and UNTRACKED closes are infrastructure leakage and must remain a separate metric.', '',
               'Row-level source files: `edgehunter_negative_entries_2026-11-16.csv` and `edgehunter_negative_demo_trades_2026-11-16.csv`.',]

    Path(args.out).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'wrote {args.out} ({len(lines)} lines)')


if __name__ == '__main__':
    main()
