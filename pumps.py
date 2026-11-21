"""Candidate price/volume event monitor.

The thresholds below are descriptive filters over closed candles.  They are
not a published pump-and-dump definition, do not establish manipulation, and
do not produce a strategy or an order.  The v2 registry intentionally rejects
these candidates until a separately sourced rule and execution contract exist.
"""
from typing import Dict, List, Optional, Sequence

PUMP = 0.15
WIN = 6
VOL_X = 3.0
LOOKBACK = 48
MAX_RANK = 30
STATS = {
    'dump': {'status': 'UNVERIFIED_CANDIDATE', 'verdict': 'НЕ подтверждено: кандидат без стратегии'},
    'pump': {'status': 'UNVERIFIED_CANDIDATE', 'verdict': 'НЕ подтверждено: кандидат без стратегии'},
}


def _atr(c: Sequence[Sequence[float]], t: int, n: int = 14) -> float:
    """Wilder's ATR(n) at candle t (levels.atr_of, the bot's one ATR) over up to 200 candles before it."""
    from levels import atr_of
    return atr_of(c[max(0, t - 200):t + 1], n) or 0.0


def scan(candles_1h: Sequence[Sequence[float]]) -> Optional[Dict]:
    """The latest pump / dump of the last LOOKBACK closed 1h candles and the state of its first pullback."""
    c = list(candles_1h)
    n = len(c)
    if n < 168 + WIN + 2:
        return None
    event = None
    for t in range(n - 1, max(168 + WIN, n - LOOKBACK) - 1, -1):
        vol7 = sum(x[5] for x in c[t - 168 - WIN:t - WIN + 1]) / (168 + 1)
        for d in (1, -1):
            seg = range(t - WIN + 1, t + 1)
            k0 = min(seg, key=lambda i: c[i][3]) if d > 0 else max(seg, key=lambda i: c[i][2])
            base = c[k0][3] if d > 0 else c[k0][2]
            move = c[t][4] / base - 1 if d > 0 else base / c[t][4] - 1
            vol = sum(x[5] for x in c[k0:t + 1])
            if move >= PUMP and vol7 and vol >= VOL_X * (t + 1 - k0) * vol7:
                event = (t, d, base, move)
                break
        if event:
            break
    if event is None:
        return None
    t, d, base, move = event
    a = _atr(c, t)
    peak = c[t][2] if d > 0 else c[t][3]
    ex = None
    for h in range(t + 1, min(n, t + 25)):
        peak = max(peak, c[h][2]) if d > 0 else min(peak, c[h][3])
        if (c[h][4] < c[h - 1][3]) if d > 0 else (c[h][4] > c[h - 1][2]):
            ex = h
            break
    if ex is None:
        # audit N26: the extreme is not confirmed yet (no exhaustion close): no zone drawn from a provisional peak
        return {'kind': 'pump' if d > 0 else 'dump', 'direction': d, 'event_ts': int(c[t][0]), 'move': move,
                'base': base, 'peak': peak, 'zone': None, 'state': 'candidate: extreme not confirmed',
                'levels': None, 'trade_dir': d, 'candidate_only': True,
                'stats': STATS['pump' if d > 0 else 'dump']}
    size = abs(peak - base)
    near, far = peak - d * 0.382 * size, peak - d * 0.618 * size
    state, pull, levels = 'ждём откат в зону', None, None
    # audit N26: the pullback is searched from the exhaustion on (the extreme's confirmation), not from t+1
    for h in range(ex, n):
        if h - t > 24 and pull is None:
            state = 'откат не пришёл за 24ч'
            break
        if pull is None:
            if (c[h][3] <= near) if d > 0 else (c[h][2] >= near):
                pull = c[h][3] if d > 0 else c[h][2]
                state = 'в зоне отката, ждём разворот на 1h'
            continue
        pull = min(pull, c[h][3]) if d > 0 else max(pull, c[h][2])
        if (pull < far) if d > 0 else (pull > far):
            state = 'откат глубже 61.8% — сценарий отменён'
            break
        if (c[h][4] > c[h - 1][2]) if d > 0 else (c[h][4] < c[h - 1][3]):
            entry = c[h][4]
            levels = {'entry': entry, 'stop': pull - d * 0.25 * a, 'tp1': peak, 'tp2': base + d * 1.618 * size}
            state = 'сигнал (закрытие 1h)' if h >= n - 2 else 'сигнал был'
            break
    return {'kind': 'pump' if d > 0 else 'dump', 'direction': d, 'event_ts': int(c[t][0]), 'move': move,
            'base': base, 'peak': peak, 'zone': sorted((near, far)), 'state': state, 'levels': levels,
            'trade_dir': d, 'candidate_only': True,
            'stats': STATS['pump' if d > 0 else 'dump']}


def monitor(markets: Dict, now_ms: float, cache: Dict) -> List[Dict]:
    """Every small cap of the universe with a pump / dump in the last 48h (cached per coin by its last 1h candle)."""
    ranked = sorted(markets.items(), key=lambda kv: -(kv[1].quote_volume_24h or 0.0))
    out = []
    for i, (sym, md) in enumerate(ranked):
        if i < MAX_RANK or not md.h1:
            continue
        key = md.h1[-1][0]
        hit = cache.get(sym)
        if hit is None or hit[0] != key:
            cache[sym] = hit = (key, scan(md.h1))
        if hit[1] is not None:
            out.append({'symbol': sym, **hit[1], 'informational': True, 'source': 'pump_monitor_v1'})
    out.sort(key=lambda r: -r['event_ts'])
    return out


def monitor_wide(h1_by_symbol: Dict, cache: Dict) -> List[Dict]:
    """The same monitor on the perpetuals outside the universe (Scanner.wide_watch_loop, eng-57: small caps by
    construction - the majors are in the universe)."""
    out = []
    for sym, h1 in list(h1_by_symbol.items()):
        if not h1:
            continue
        hit = cache.get(sym)
        if hit is None or hit[0] != h1[-1][0]:
            cache[sym] = hit = (h1[-1][0], scan(h1))
        if hit[1] is not None:
            out.append({'symbol': sym, **hit[1], 'informational': True, 'source': 'pump_monitor_v1'})
    out.sort(key=lambda r: -r['event_ts'])
    return out
