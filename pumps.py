"""
Live pump / dump monitor of small caps (the rules of `research_pumps.py`, on each coin's closed 1h candles).

A PUMP: the close >= 15% above the lowest low of the last 6 hours, the hours since that low traded >= 3x the average
hour of the week before (DUMP: the mirror). Small caps only (not among the 30 most traded coins by 24h volume).
After the event the monitor follows the first pullback / bounce: the 38.2-61.8% zone of the move, the trigger (a 1h
close beyond the previous candle's extreme after the zone was touched), stop beyond the pullback's extreme (+ 0.25
ATR1h), TP1 = the move's extreme, TP2 = its 1.618 extension.

Measured (research/pumps.md, research/pumps_holdout.md; hit rate vs the random-walk rate of the same trade):
- after a DUMP, short the first bounce: 2023-10..2026-08 +0.17R / +0.16R (older / newer half), the untouched
  2021-04..2023-09 +0.36R / +0.34R, TP1 hit 62-69% vs 45-57% geometry: the one pre-registered part that held;
- after a PUMP, buy the first pullback: +0.13R / +0.14R in 2023-26 but -0.04R / +0.13R in 2021-23 with the hit
  rate AT the geometry: not confirmed.
Information, never an order; samples are small (a few hundred trades per period).
"""
from typing import Dict, List, Optional, Sequence

PUMP = 0.15
WIN = 6
VOL_X = 3.0
LOOKBACK = 48
MAX_RANK = 30
STATS = {
    'dump': {'label': 'шорт первого отскока после дампа', 'verdict': 'подтверждено на 2021–23',
             'r': '+0.16…+0.36R', 'hit': '62–69% при геометрии 45–57%'},
    'pump': {'label': 'покупка первого отката после пампа', 'verdict': 'НЕ подтверждено на 2021–23',
             'r': '−0.04…+0.14R', 'hit': '50–58% при геометрии 48–52%'},
}


def _atr(c: Sequence[Sequence[float]], t: int, n: int = 14) -> float:
    trs = [max(c[i][2] - c[i][3], abs(c[i][2] - c[i - 1][4]), abs(c[i][3] - c[i - 1][4]))
           for i in range(max(1, t - n + 1), t + 1)]
    return sum(trs) / len(trs) if trs else 0.0


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
    for h in range(t + 1, min(n, t + 25)):
        peak = max(peak, c[h][2]) if d > 0 else min(peak, c[h][3])
        if (c[h][4] < c[h - 1][3]) if d > 0 else (c[h][4] > c[h - 1][2]):
            break
    size = abs(peak - base)
    near, far = peak - d * 0.382 * size, peak - d * 0.618 * size
    state, pull, levels = 'ждём откат в зону', None, None
    for h in range(t + 1, n):
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
            'trade_dir': d, 'stats': STATS['pump' if d > 0 else 'dump']}


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
            out.append({'symbol': sym, **hit[1]})
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
            out.append({'symbol': sym, **hit[1]})
    out.sort(key=lambda r: -r['event_ts'])
    return out
