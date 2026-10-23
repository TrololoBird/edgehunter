"""
Loop-side setup detectors (eng-59, B9): the strategies the scanner checks on the final 1m candles / daily candles of
each coin rather than in the maps worker - the pump start / top, the Silver Bullet, PO3, the Turtles' touch, Crabel's
ORB, the OI signal, the dump bounce, Connors' RSI(2). Moved out of scanner.Scanner so the archive replay
(replay.py) runs the SAME code as the live bot. `md` is the coin's MarketData (or the replay's stand-in with the same
fields: d1, h1, tier0, oi_samples, minute_closed_until); `minutes_of(symbol)` returns the FINAL 1m futures candles,
`m15_of(symbol)` the closed 15m candles [ts, o, h, l, c, quote_vol, taker_buy].
"""
from typing import Callable, Dict, List, Optional

from config import CONFIG
from levels import resample


class LoopDetectors:
    def __init__(self, minutes_of: Callable[[str], List], m15_of: Callable[[str], List]):
        self.minutes_of = minutes_of
        self.m15_of = m15_of
        # audit (dump bounce): the coin's rank by 24h quote volume among the markets (1 = the largest), None unknown;
        # set by the scanner / the replay - the research measured small caps OUTSIDE the top 30, not 'not one of 5'
        self.volume_rank: Callable[[str], Optional[int]] = lambda symbol: None
        self._connors_checked: Dict[str, int] = {}   # symbol -> the daily close Connors' RSI(2) was checked at
        self._turtle_checked: Dict[str, int] = {}    # symbol -> the last final minute the Turtle channel was checked on
        self._turtle_fired: set = set()              # (symbol, direction, day) breakouts already fired
        self._orb_checked: Dict[str, int] = {}       # symbol -> the last final minute Crabel's ORB was checked on
        self._orb_fired: set = set()                 # (symbol, day) ORBs already fired (one a day)
        self._orb_open_fired: set = set()            # eng-150: the shadow ORB at a fixed 13:30 UTC open
        self.orb_shadow: List[Dict] = []             # eng-150: its events, journaled by the scanner WITHOUT a card
        self._orb_day: Dict[str, Dict] = {}          # symbol -> the UTC day's open and extremes so far (ORB)
        self._oi_build_checked: Dict[str, int] = {}  # eng-88: symbol -> the last final minute the OI build was checked on
        self._oi_build_fired: set = set()            # (symbol, hour) OI builds already fired
        self._dump_checked: Dict[str, int] = {}      # symbol -> the last closed 1h candle the dump bounce was checked on
        self._dump_fired: set = set()                # (symbol, dump hour) bounces already fired
        self._sb_checked: Dict[str, int] = {}        # symbol -> the last final minute the Silver Bullet was checked on
        self._sb_fired: set = set()                  # (symbol, direction, window start) setups already fired
        self._po3_checked: Dict[str, int] = {}       # eng-58: ICT Power of Three, as the Silver Bullet
        self._po3_fired: set = set()
        self._pump_checked: Dict[str, int] = {}      # symbol -> the last final minute the pump checks ran on
        self._pump_fired: set = set()                # pump starts / tops already fired
        self.skip_log: List[tuple] = []              # eng-132: (symbol, strategy, held, needed): a history gate said no
        self._skip_seen: set = set()                 # (symbol, strategy) already in skip_log since the last drain

    def _skip(self, symbol: str, strategy: str, held: int, needed: int) -> None:
        """One skip_log row per coin and strategy until the log is drained (replay never drains: no unbounded growth)."""
        if (symbol, strategy) not in self._skip_seen and len(self.skip_log) < 5000:
            self._skip_seen.add((symbol, strategy))
            self.skip_log.append((symbol, strategy, held, needed))

    def scan(self, symbol: str, md, now_ms: int) -> List[Dict]:
        """Every loop-side setup of the coin this scan (in the scanner's order)."""
        out: List[Dict] = []
        for fn in (self._connors_daily, self._turtle_breakout, self._orb_touch, self._dump_bounce,
                   self._oi_build, self._po3, self._silver_bullet):
            found = fn(symbol, md, now_ms)
            if isinstance(found, list):
                out.extend(found)
            elif found:
                out.append(found)
        out.extend(self._pumps(symbol, md, now_ms))
        return out

    def _pumps(self, symbol: str, md, now_ms: int) -> List[Dict]:
        """The pump's start (every final minute) and top (every 15m close), cheap gates first (strategies.pump)."""
        from strategies.pump import pump_start, pump_top
        minute = md.minute_closed_until
        if not minute or self._pump_checked.get(symbol) == minute:
            return []
        self._pump_checked[symbol] = minute
        minutes = self.minutes_of(symbol)
        if len(minutes) < 120:
            self._skip(symbol, 'pump', len(minutes), 120)
            return []
        out = []
        cfg = CONFIG.strategies
        from strategies.oi_build import _close_at
        base15 = _close_at(minutes, int(minutes[-1][0]) - 15 * 60_000)     # by time (eng-74), None across a gap
        if base15 and minutes[-1][4] / base15 - 1 >= cfg.pump_start_min_pct:
            closes = [c[4] for c in self.m15_of(symbol)[-97:]]
            rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
            vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 if len(rets) > 20 else None
            found = pump_start(minutes, md.tier0 or {}, vol, now_ms, list(md.h1 or ()))
            if found and (symbol, found['anchor_ts'] // 3_600_000) not in self._pump_fired:
                self._pump_fired.add((symbol, found['anchor_ts'] // 3_600_000))
                out.append(found)
        if (minute + 60_000) % 900_000 == 0:
            window = [c for c in minutes if c[0] >= minute - 4 * 3_600_000]
            if window and max(c[2] for c in window) / min(c[3] for c in window) - 1 >= cfg.pump_top_min_pct:
                found = pump_top(minutes, md.tier0 or {}, minute + 60_000)
                if found and (symbol, 'top', found['anchor_ts']) not in self._pump_fired:
                    self._pump_fired.add((symbol, 'top', found['anchor_ts']))
                    out.append(found)
        return out

    def _silver_bullet(self, symbol: str, md, now_ms: int) -> Optional[Dict]:
        """ICT's Silver Bullet (strategies.silver_bullet), only inside its New York windows, once per window and
        direction per coin, on each new final 5m bar."""
        from strategies.silver_bullet import FIVE_MS, silver_bullet, window_of
        start = window_of(now_ms)
        minute = md.minute_closed_until
        if start is None or not minute or (minute + 60_000) % FIVE_MS:
            return None
        if self._sb_checked.get(symbol) == minute:
            return None
        self._sb_checked[symbol] = minute
        # eng-106: from 20:00 NY the evening before (the Asian / London session pools), the 1m history holds 10h
        bars = resample([c for c in self.minutes_of(symbol) if c[0] >= start - 10 * 3_600_000], 5,
                        minute + 60_000)
        # the session pools older than the 1m history (Asia ends 10h before the 10:00 NY window): closed 15m candles
        first = bars[0][0] if bars else minute
        bars = [list(c) for c in self.m15_of(symbol) if start - 16 * 3_600_000 <= c[0] and c[0] + 900_000 <= first] + bars
        # ICT's draw: the previous day's high / low (the last closed daily candle)
        pd = md.d1[-1] if md.d1 else None
        found = silver_bullet(bars, now_ms, pdh=pd[2] if pd else None, pdl=pd[3] if pd else None,
                              skip=[d for d in (1, -1) if (symbol, d, start) in self._sb_fired])
        if found is None:
            return None
        key = (symbol, found['direction'], start)
        if key in self._sb_fired:
            return None
        self._sb_fired.add(key)
        return found

    def _po3(self, symbol: str, md, now_ms: int) -> Optional[Dict]:
        """ICT's Power of Three / Judas swing (strategies.po3) in the London kill zone, on each new final 5m bar, once
        per coin, day and direction."""
        from strategies.po3 import FIVE_MS, london_window, po3
        w = london_window(now_ms)
        minute = md.minute_closed_until
        if w is None or not minute or (minute + 60_000) % FIVE_MS:
            return None
        if self._po3_checked.get(symbol) == minute:
            return None
        self._po3_checked[symbol] = minute
        bars = resample([c for c in self.minutes_of(symbol) if c[0] >= w[2]], 5, minute + 60_000)
        pd = md.d1[-1] if md.d1 else None
        found = po3(bars, now_ms, pdh=pd[2] if pd else None, pdl=pd[3] if pd else None,
                    skip=[d for d in (1, -1) if (symbol, d, w[0]) in self._po3_fired])
        if found is None:
            return None
        key = (symbol, found['direction'], w[0])
        if key in self._po3_fired:
            return None
        self._po3_fired.add(key)
        return found

    def _turtle_breakout(self, symbol: str, md, now_ms: int) -> Optional[Dict]:
        """The Turtles' channel breakout on the touch (strategies.turtle), checked on each new final minute, once per
        coin, direction and day."""
        if len(md.d1) < 60:
            self._skip(symbol, 'breakout', len(md.d1), 60)
            return None
        minute = md.minute_closed_until
        if not minute or self._turtle_checked.get(symbol) == minute:
            return None
        self._turtle_checked[symbol] = minute
        minutes = self.minutes_of(symbol)
        day_start = int(now_ms // 86_400_000 * 86_400_000)
        today = [c for c in minutes if c[0] >= day_start]
        if not today or int(md.d1[-1][0]) + 86_400_000 < day_start:
            return None                           # yesterday's daily candle not loaded yet
        last = today[-1]
        # cheap gate first: the minute reached the nearer of the 20 / 55-day channels at all (building the 15m candles
        # of every coin each minute stalled the loop 1.4s live)
        recent = md.d1[-20:]
        if not (last[2] > max(c[2] for c in recent) or last[3] < min(c[3] for c in recent)) and                 not (last[2] > max(c[2] for c in md.d1[-55:]) or last[3] < min(c[3] for c in md.d1[-55:])):
            return None
        # today's range BEFORE the last final minute: the 15m candles of the day (complete from 00:00 UTC whatever
        # the 1m history holds after a restart) plus the earlier minutes
        m15 = [c for c in self.m15_of(symbol) if day_start <= c[0] < last[0] // 900_000 * 900_000]
        earlier = [c for c in today[:-1]] + m15
        if not earlier:
            return None                           # no record of the day before this minute: cannot tell a fresh touch
        from strategies.turtle import turtle_breakout
        found = turtle_breakout(md.d1, last[2], last[3], int(last[0]),
                                max(c[2] for c in earlier), min(c[3] for c in earlier))
        if found is None:
            return None
        key = (symbol, found['direction'], day_start)
        if key in self._turtle_fired:
            return None
        self._turtle_fired.add(key)
        return found

    def _orb_touch(self, symbol: str, md, now_ms: int) -> Optional[Dict]:
        """eng-93: the session ORB (strategies.classic.session_orb) on the majors, gold, silver and oil only: the first
        break of the Asia / London / New York opening range, on the final minute or the live trade price (Crabel's
        entries are stop orders resting at the levels - eng-82)."""
        base = symbol.split('/')[0]
        if base not in CONFIG.strategies.orb_bases:
            return None
        minutes = self.minutes_of(symbol)
        if not minutes:
            return None
        last = minutes[-1]
        hi, lo = last[2], last[3]
        samples = getattr(md, 'ticker_samples', None)
        if samples and now_ms - samples[-1][0] <= 5_000:
            hi, lo = max(hi, samples[-1][1]), min(lo, samples[-1][1])
        from strategies.classic import session_orb
        d1 = list(getattr(md, 'd1', None) or [])
        # eng-150 (plan, shadow): the New York ORB from a FIXED 13:30 UTC open (the US cash open in EDT) to 20:00 UTC,
        # weekdays - never a card, only a journal row (vetoed 'variant_orb_open') beside the live session ORB
        day = now_ms // 86_400_000 * 86_400_000
        o, c = day + 48_600_000, day + 72_000_000
        if (now_ms // 86_400_000 + 3) % 7 < 5 and o <= now_ms < c:
            found = session_orb(base, minutes, now_ms, hi, lo, self._orb_open_fired, symbol, d1,
                                sessions=[('NY 13:30 UTC', o, c)])
            if found is not None:
                found['symbol'] = symbol
                self.orb_shadow.append(found)
        return session_orb(base, minutes, now_ms, hi, lo, self._orb_fired, symbol, d1)

    def _oi_build(self, symbol: str, md, now_ms: int) -> Optional[Dict]:
        """eng-127, Pring's OI rule in shadow (strategies.oi_build): at 5m closes, once per coin per hour."""
        minute = md.minute_closed_until
        # eng-105, the owner: no entry on a 1m spike - the conditions are read at a 5m candle's CLOSE (the last
        # final minute ends a 5m bar, so its close is the 5m close)
        if not minute or self._oi_build_checked.get(symbol) == minute or (minute + 60_000) % 300_000:
            return None
        self._oi_build_checked[symbol] = minute
        from strategies.oi_build import oi_build
        found = oi_build(self.minutes_of(symbol), list(getattr(md, 'oi_5m', None) or []), now_ms)
        if found is None:
            return None
        key = (symbol, now_ms // 3_600_000)
        if key in self._oi_build_fired:
            return None
        self._oi_build_fired.add(key)
        return found

    def _dump_bounce(self, symbol: str, md, now_ms: int) -> Optional[Dict]:
        """The short of the first bounce after a dump (strategies.pump.dump_bounce) on each closed 1h candle."""
        h1 = list(md.h1)
        if len(h1) < 190:
            self._skip(symbol, 'pump', len(h1), 190)
            return None
        closed = int(h1[-1][0])
        if self._dump_checked.get(symbol) == closed:
            return None
        self._dump_checked[symbol] = closed
        from strategies.pump import MAJORS, dump_bounce
        if symbol.split('/')[0] in MAJORS:
            return None                           # measured on small caps (research_pumps: majors apart)
        rank = self.volume_rank(symbol)
        if rank is None or rank <= 30:
            return None       # small caps outside the top 30 by volume only; an unknown rank = not the studied class
        found = dump_bounce(h1, now_ms)
        if found is None or (symbol, found['anchor_ts']) in self._dump_fired:
            return None
        self._dump_fired.add((symbol, found['anchor_ts']))
        return found

    def _connors_daily(self, symbol: str, md, now_ms: int) -> Optional[Dict]:
        """Connors' RSI(2) on the coin's daily candles, once per closed day (fresh within the day's first 2 hours)."""
        if len(md.d1) < 202:
            self._skip(symbol, 'connors', len(md.d1), 202)
            return None
        day_close = int(md.d1[-1][0]) + 86_400_000
        if self._connors_checked.get(symbol) == day_close or now_ms - day_close > 2 * 3_600_000:
            return None
        self._connors_checked[symbol] = day_close
        from strategies.classic import connors_event
        found = [e for e in (connors_event(md.d1), connors_event(md.d1, first='orig')) if e]
        return found or None

