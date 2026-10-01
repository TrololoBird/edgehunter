"""
Auction-theory engine ported from crypto_maniac's auction_theory_in_code (strategy.py + vprofile.py), 1h candles.

1. A clear consolidation: sliding windows of 24 / 48 / 96 bars whose range is <= 6 ATR and <= 10% of the price, with
   no trend inside (|net| / range <= 0.35), and a concentrated volume profile (POC bin >= 2.5x uniform, not within
   15% of the range's edges). Such a window lives as a Candidate while it keeps qualifying.
2. The impulse: once price closes out of the candidate, the extreme within 12 bars runs >= 1 range height beyond the
   edge -> the POC becomes a Level with the impulse's direction.
3. Retest and reaction: price returns into the level's zone (+-0.25 ATR); the side it came from (by the previous
   closes) gives the trade: from above -> long, from below -> short. A close >= 0.15 ATR beyond the level toward the
   trade within 3 bars is the reaction (the signal); a close >= 0.9 ATR against fails the test. A level gives at most
   2 tests, dies after 6 crosses or 1500 bars.
4. Stop beyond the test's extreme (and the level) + 0.35 ATR; target = the nearest STRONG (conc >= 2.8) level not
   tested yet in the trade's direction, skipped when its R:R < 1.5; without one, 2.5 R.

Causal by construction (bars fed one by one). The engine keeps its state between calls in the maps worker process
(ENGINES): each 1h close feeds only the new bars; a gap / a restart rebuilds it from the history it is given.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from config import CONFIG


def volume_profile(high, low, volume, bins: int, pmin: float, pmax: float, va_pct: float = 0.70):
    """Volume of each candle spread over price bins by overlap; returns (poc, val, vah, poc_share, total)."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    volume = np.asarray(volume, dtype=float)
    lo, hi = np.minimum(low, high), np.maximum(low, high)
    if pmax <= pmin:
        pmax = pmin + max(abs(pmin) * 1e-6, 1e-12)
    bins = max(int(bins), 2)
    edges = np.linspace(pmin, pmax, bins + 1)
    hist = np.zeros(bins, dtype=float)
    span = hi - lo
    point = span <= 0
    if point.any():
        idx = np.clip(np.searchsorted(edges, lo[point], side="right") - 1, 0, bins - 1)
        np.add.at(hist, idx, volume[point])
    norm = ~point
    if norm.any():
        lo_n, hi_n = lo[norm][:, None], hi[norm][:, None]
        left = np.maximum(edges[None, :-1], lo_n)
        right = np.minimum(edges[None, 1:], hi_n)
        w = np.clip(right - left, 0.0, None) / (hi_n - lo_n)
        hist += (w * volume[norm][:, None]).sum(axis=0)
    total = float(hist.sum())
    if total <= 0:
        return 0.5 * (pmin + pmax), pmin, pmax, 0.0, 0.0
    p = int(hist.argmax())
    poc = 0.5 * (edges[p] + edges[p + 1])
    in_va = {p}
    acc = float(hist[p])
    left_i, right_i = p - 1, p + 1
    while acc < va_pct * total and (left_i >= 0 or right_i < bins):
        lv = float(hist[left_i]) if left_i >= 0 else -1.0
        rv = float(hist[right_i]) if right_i < bins else -1.0
        if rv >= lv:
            acc += max(rv, 0.0)
            in_va.add(right_i)
            right_i += 1
        else:
            acc += max(lv, 0.0)
            in_va.add(left_i)
            left_i -= 1
    return float(poc), float(edges[min(in_va)]), float(edges[max(in_va) + 1]), float(hist[p] / total), total


@dataclass
class Candidate:
    poc: float
    val: float
    vah: float
    conc: float
    win_lo: float
    win_hi: float
    rng: float
    length: int
    start: int
    end: int
    last_seen: int


@dataclass
class Watch:
    cand: Candidate
    break_i: int
    hi_ext: float = 0.0
    lo_ext: float = 0.0
    done: bool = False


@dataclass
class PendingTest:
    dir: int
    start: int
    extreme: float


@dataclass
class Level:
    price: float
    val: float
    vah: float
    conc: float
    win_lo: float
    win_hi: float
    rng: float
    cons_len: int
    created_idx: int
    impulse_dir: int
    created_ts: int = 0
    touches: int = 0
    crosses: int = 0
    tested: bool = False
    active: bool = True
    alive: bool = True
    side: int = 0
    cooldown_until: int = -1
    pending: Optional[PendingTest] = None


class AuctionEngine:
    """Incremental engine of one symbol (closed bars in time order)."""

    def __init__(self):
        self.cfg = CONFIG.strategies
        self.symbol: Optional[str] = None       # set by auction_signals (the measured pierce is per coin)
        self.h: List[float] = []
        self.sub: Dict[int, list] = {}         # hour open ms -> its 15m (high, low, quote volume)
        self.l: List[float] = []
        self.c: List[float] = []
        self.v: List[float] = []
        self.ts: List[int] = []
        self.atr_vals: List[float] = []
        self._atr: Optional[float] = None
        self._tr_seed: List[float] = []
        self.candidates: List[Candidate] = []
        self.watches: List[Watch] = []
        self.levels: List[Level] = []
        self.i = -1

    def on_bar(self, ts: int, h: float, l: float, c: float, v: float) -> List[Dict]:
        cfg = self.cfg
        self.i += 1
        i = self.i
        self.h.append(float(h))
        self.l.append(float(l))
        self.c.append(float(c))
        self.v.append(float(v))
        self.ts.append(int(ts))
        tr = self.h[0] - self.l[0] if i == 0 else max(h - l, abs(h - self.c[i - 1]), abs(l - self.c[i - 1]))
        n = cfg.auction_atr_period
        atr = float('nan')
        if i < n:
            self._tr_seed.append(tr)
            if i == n - 1:
                self._atr = sum(self._tr_seed) / n
                atr = self._atr
        else:
            self._atr = (self._atr * (n - 1) + tr) / n
            atr = self._atr
        self.atr_vals.append(atr)
        signals: List[Dict] = []
        if not np.isfinite(atr) or atr <= 0:
            return signals
        self._update_levels(i, h, l, c, atr, signals)
        self._update_watches(i)
        self._update_candidates(i, c, atr)
        self._scan_windows(i, atr)
        return signals

    # -------------------------------------------------------------- levels

    def _update_levels(self, i, h, l, c, atr, signals):
        cfg = self.cfg
        from pierce import overshoot
        for lvl in self.levels:
            if not lvl.alive:
                continue
            # a touch = price within the usual pierce of a 1h level (p50, pierce.py) of the POC, not +-0.25 ATR
            tol = overshoot(self.symbol, 'swing_1h', lvl.price, 'p50') or cfg.auction_touch_atr * atr
            if i - lvl.created_idx > cfg.auction_level_ttl:
                lvl.alive = False
                continue
            zone_lo, zone_hi = lvl.price - tol, lvl.price + tol
            touched = l <= zone_hi and h >= zone_lo
            prev_side = lvl.side
            if lvl.pending is not None:
                sig = self._progress_test(lvl, i, h, l, c, atr)
                if sig is not None:
                    signals.append(sig)
            elif touched and lvl.active and lvl.touches < cfg.auction_max_touches and i >= lvl.cooldown_until \
                    and prev_side != 0:
                lvl.pending = PendingTest(dir=prev_side, start=i, extreme=l if prev_side > 0 else h)
                sig = self._progress_test(lvl, i, h, l, c, atr)
                if sig is not None:
                    signals.append(sig)
            if touched:
                lvl.tested = True
            new_side = 1 if c > zone_hi else -1 if c < zone_lo else 0
            if new_side != 0:
                if prev_side != 0 and new_side != prev_side:
                    lvl.crosses += 1
                    lvl.tested = True
                    if lvl.crosses > cfg.auction_max_crosses:
                        lvl.active = False
                lvl.side = new_side

    def _progress_test(self, lvl: Level, i, h, l, c, atr) -> Optional[Dict]:
        cfg = self.cfg
        p = lvl.pending
        d = p.dir
        p.extreme = min(p.extreme, l) if d > 0 else max(p.extreme, h)
        failed = (lvl.price - c) * d >= cfg.auction_invalidation_atr * atr
        success = (c - lvl.price) * d >= cfg.auction_reaction_atr * atr
        expired = (i - p.start) >= cfg.auction_reaction_window

        def close_test():
            lvl.pending = None
            lvl.touches += 1
            lvl.tested = True
            lvl.cooldown_until = i + cfg.auction_level_cooldown
            if lvl.touches >= cfg.auction_max_touches:
                lvl.active = False

        if failed:
            close_test()
            return None
        if success:
            close_test()
            return self._make_signal(lvl, d, i, c, atr, p)
        if expired:
            close_test()
        return None

    def _make_signal(self, lvl: Level, d: int, i: int, c: float, atr: float, p: PendingTest) -> Optional[Dict]:
        cfg = self.cfg
        entry = c
        base = min(p.extreme, lvl.price) if d > 0 else max(p.extreme, lvl.price)
        from pierce import overshoot
        # beyond the test's extreme by the usual pierce (p80) of a 1h level, as every structural stop (was 0.35 ATR)
        pad = overshoot(self.symbol, 'swing_1h', base, 'p80')
        stop = base - d * (pad if pad is not None else cfg.auction_stop_pad_atr * atr)
        risk = (entry - stop) * d
        if risk < cfg.auction_min_risk_atr * atr:
            return None
        cands = [x for x in self.levels if x is not lvl and x.alive and not x.tested
                 and x.conc >= cfg.auction_strong_concentration and (x.price - entry) * d > 0.1 * atr]
        target = None
        if cands:
            target = min(cands, key=lambda x: (x.price - entry) * d).price
            if (target - entry) * d / risk < cfg.auction_min_rr:
                return None
        kind = 'local' if (i - lvl.created_idx) <= cfg.auction_local_window else 'retest'
        return {'direction': d, 'entry': entry, 'stop': stop, 'target': target, 'level': lvl.price,
                'conc': lvl.conc, 'kind': kind, 'extreme': p.extreme, 'atr': atr, 'ts': self.ts[i],
                'level_ts': lvl.created_ts, 'impulse_dir': lvl.impulse_dir}

    # ------------------------------------------------------------- watches

    def _update_watches(self, i):
        for w in self.watches:
            if not w.done:
                self._feed_watch(w, i)
        self.watches = [w for w in self.watches if not w.done]

    def _feed_watch(self, w: Watch, i: int):
        cfg = self.cfg
        cand = w.cand
        w.hi_ext = max(w.hi_ext, self.h[i] - cand.win_hi)
        w.lo_ext = max(w.lo_ext, cand.win_lo - self.l[i])
        thr = cfg.auction_impulse_mult * cand.rng
        up, dn = w.hi_ext >= thr, w.lo_ext >= thr
        if up and dn:
            w.done = True
        elif up or dn:
            self._create_level(cand, 1 if up else -1, i)
            w.done = True
        elif i - w.break_i >= cfg.auction_impulse_horizon:
            w.done = True

    def _create_level(self, cand: Candidate, direction: int, i: int):
        atr = self.atr_vals[i]
        c_now = self.c[i]
        for lvl in self.levels:
            if lvl.alive and abs(lvl.price - cand.poc) <= 0.5 * atr:
                lvl.price, lvl.val, lvl.vah = cand.poc, cand.val, cand.vah
                lvl.conc = max(lvl.conc, cand.conc)
                lvl.win_lo, lvl.win_hi, lvl.rng, lvl.cons_len = cand.win_lo, cand.win_hi, cand.rng, cand.length
                lvl.created_idx, lvl.created_ts, lvl.impulse_dir = i, self.ts[i], direction
                lvl.touches = lvl.crosses = 0
                lvl.tested, lvl.active, lvl.alive, lvl.pending, lvl.cooldown_until = False, True, True, None, -1
                lvl.side = 1 if c_now > lvl.price else -1
                return
        self.levels.append(Level(price=cand.poc, val=cand.val, vah=cand.vah, conc=cand.conc, win_lo=cand.win_lo,
                                 win_hi=cand.win_hi, rng=cand.rng, cons_len=cand.length, created_idx=i,
                                 impulse_dir=direction, created_ts=self.ts[i], side=1 if c_now > cand.poc else -1))
        if len(self.levels) > self.cfg.auction_max_levels:
            self.levels.sort(key=lambda x: x.created_idx)
            self.levels = self.levels[-self.cfg.auction_max_levels:]

    # ---------------------------------------------------------- candidates

    def _update_candidates(self, i, c, atr):
        keep = []
        for cand in self.candidates:
            if c > cand.win_hi + 0.05 * atr or c < cand.win_lo - 0.05 * atr:
                w = Watch(cand=cand, break_i=i)
                self._feed_watch(w, i)
                if not w.done:
                    self.watches.append(w)
            elif i - cand.last_seen <= self.cfg.auction_candidate_stale:
                keep.append(cand)
        self.candidates = keep

    def _scan_windows(self, i, atr):
        cfg = self.cfg
        matched: List[float] = []
        for length in sorted(cfg.auction_windows, reverse=True):
            if i + 1 < length:
                continue
            s = i + 1 - length
            hh, ll = np.asarray(self.h[s:i + 1]), np.asarray(self.l[s:i + 1])
            cc, vv = np.asarray(self.c[s:i + 1]), np.asarray(self.v[s:i + 1])
            win_hi, win_lo = float(hh.max()), float(ll.min())
            rng = win_hi - win_lo
            if rng <= 0 or rng > cfg.auction_max_range_atr * atr:
                continue
            mid = float(cc.mean())
            if mid <= 0 or rng / mid > cfg.auction_max_range_pct:
                continue
            if abs(float(cc[-1]) - float(cc[0])) / rng > cfg.auction_max_net_ratio:
                continue
            bins = int(np.clip(round(rng / (cfg.auction_bin_atr * atr)), 12, 60))
            parts = [self.sub.get(t) for t in self.ts[s:i + 1]]
            if all(p and len(p) == 4 for p in parts):
                flat = [q for p in parts for q in p]
                poc, val, vah, share, total = volume_profile(np.asarray([q[0] for q in flat]), np.asarray([q[1] for q in flat]),
                                                             np.asarray([q[2] for q in flat]), bins, win_lo, win_hi)
            else:
                poc, val, vah, share, total = volume_profile(hh, ll, vv, bins, win_lo, win_hi)
            if total <= 0:
                continue
            conc = share * bins
            if conc < cfg.auction_min_concentration:
                continue
            pos = (poc - win_lo) / rng
            if pos < cfg.auction_poc_edge or pos > 1 - cfg.auction_poc_edge:
                continue
            if any(abs(poc - z) <= 0.6 * atr for z in matched):
                continue
            matched.append(poc)
            found = next((x for x in self.candidates if abs(x.poc - poc) <= 0.6 * atr), None)
            if found is not None:
                found.poc, found.val, found.vah = poc, val, vah
                found.conc = max(found.conc, conc)
                found.win_lo, found.win_hi, found.rng, found.length = win_lo, win_hi, rng, length
                found.start, found.end, found.last_seen = s, i, i
            else:
                self.candidates.append(Candidate(poc, val, vah, conc, win_lo, win_hi, rng, length, s, i, i))
                if len(self.candidates) > 6:
                    self.candidates.sort(key=lambda x: x.last_seen)
                    self.candidates = self.candidates[-6:]

    def naked_strong(self, price: float, direction: int, atr: float) -> List[float]:
        """Strong untested levels beyond `price` in the direction (targets), nearest first."""
        out = [x.price for x in self.levels if x.alive and not x.tested
               and x.conc >= self.cfg.auction_strong_concentration and (x.price - price) * direction > 0.1 * atr]
        return sorted(out, key=lambda p: (p - price) * direction)


# symbol -> engine (lives in the maps worker process between 15m closes)
ENGINES: Dict[str, AuctionEngine] = {}


def auction_signals(symbol: str, candles_1h: Sequence[Sequence[float]],
                    candles_15m: Sequence[Sequence[float]] = ()) -> List[Dict]:
    """
    `candles_15m`: the POC is built from them where they cover a window (volume at price needs candles short against
    the window: 1h candles put a 4-day POC 3% off, 15m matched 1m within a bucket - Dalton's profile is volume AT price).
    Feed the closed 1h candles the symbol's engine has not seen; returns the signals of the NEW bars. A history that
    does not continue the engine's (a gap, a restart) rebuilds the engine silently: its warm-up bars give no signals.
    """
    if not candles_1h:
        return []
    subs: Dict[int, list] = {}
    for c in candles_15m:
        subs.setdefault(int(c[0]) // 3_600_000 * 3_600_000, []).append((float(c[2]), float(c[3]), float(c[5])))
    engine = ENGINES.get(symbol)
    if engine is not None:
        engine.symbol = symbol
        engine.sub.update(subs)
    last = engine.ts[-1] if engine is not None and engine.ts else None
    if last is None or not any(int(c[0]) == last for c in candles_1h[-50:]) or int(candles_1h[-1][0]) < last:
        engine = ENGINES[symbol] = AuctionEngine()
        engine.symbol = symbol
        engine.sub.update(subs)
        for c in candles_1h[:-1]:
            engine.on_bar(int(c[0]), c[2], c[3], c[4], c[5])
        new = candles_1h[-1:]
    else:
        new = [c for c in candles_1h if int(c[0]) > last]
    out: List[Dict] = []
    for c in new:
        out.extend(engine.on_bar(int(c[0]), c[2], c[3], c[4], c[5]))
    return out
