"""
Browser dashboard: an aiohttp server inside the bot, bound to localhost only.

- GET /            the page (web/index.html + app.js + style.css, no build step)
- GET /ws          full state as JSON after every scan (cards, forming / vetoed setups, anomalies, session, venues,
                   ML, market header)
- GET /api/coin    one coin: 1h / 15m / 5m candles, the level map (zones.py) or the card's plan, the order-book
                   heatmap (hot coins), journal rows of 48h
- GET /api/history finished cards / anomalies / entries of the last N hours with what price did afterwards, raw and
                   against the whole-universe mean (the journal's `universe` snapshots)
- GET /api/anomaly_stats  per anomaly label: count and the average move afterwards in its direction
- GET /api/stats   stats.py report rendered to HTML

Journal queries use their own read-only SQLite connection (WAL: readers never block the bot's writer) in a worker
thread. Nothing here is advice: the page shows mechanical rules and their measured results.
"""
import asyncio
import io
import logging
import math
import os
import sqlite3
import statistics
import time

import pumps
import webbrowser
from typing import Dict, List, Optional

import orjson
import aiohttp
from aiohttp import WSMsgType, web

from config import CONFIG
from journal import HORIZONS
from scorer import LONG_PHASES, PHASE_MAX, SHORT_PHASES
from strategies import SETUPS, confirm

PHASE_NAMES = {'A': 'accumulation', 'B': 'spring', 'C': 'distribution', 'D': 'breakdown', 'E': 'capitulation',
               'F': 'markup'}

logger = logging.getLogger(__name__)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')


# ---------------------------------------------------------------------------------------------------- text helpers

def _usd(value: float) -> str:
    for divisor, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= divisor:
            scaled = value / divisor
            return f"{scaled:.0f}{suffix}" if abs(scaled) >= 100 else f"{scaled:.1f}{suffix}"
    return f"{value:.0f}"


def _pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:+.{digits}f}%"


def _buyers(delta_ratio: float) -> str:
    return f"{(1 + delta_ratio) / 2 * 100:.0f}%"


def explain(group_key: str, sig: Dict) -> List[str]:
    """Plain-language conditions behind a setup."""
    parts = group_key.split()
    phase = parts[1].upper() if len(parts) > 1 and group_key.startswith(('BULL ', 'BEAR ')) else ''
    reasons: List[str] = []
    if sig.get('setup_note'):
        # A detected setup (sweep / exhaustion / absorption / breakout) describes itself
        reasons = [sig['setup_note']]
    elif group_key.startswith('IMPULSE'):
        reasons = [f"{_pct(sig.get('price_change_5m', 0.0))}/5m", f"OI {_pct(sig.get('oi_change_5m', 0.0))}",
                   f"buyers {_buyers(sig.get('delta_ratio', 0.0))}", f"vol 1m {sig.get('rvol_1m', 0.0):.1f}x"]
    elif phase == 'A':
        if sig.get('is_squeezed'):
            reasons.append("squeeze")
        reasons += [f"range {sig.get('flat_range_atr', 0.0):.1f} ATR/2.5h",
                    f"sells absorbed (sellers {_buyers(-sig.get('flow_flat', 0.0))})",
                    f"OI {_pct(sig.get('oi_change_flat', 0.0))}"]
    elif phase == 'B':
        reasons = ["swept range low & reclaimed", f"sells absorbed (buyers {_buyers(sig.get('delta_ratio', 0.0))})",
                   f"vol {sig.get('rvol_15m', 0.0):.1f}x"]
    elif phase == 'E':
        reasons = [f"climax vol {sig.get('rvol_15m', 0.0):.1f}x", f"OI {_pct(sig.get('oi_change_1h', 0.0))}/1h",
                   f"fund {_pct(sig.get('funding_rate', 0.0), 3)}", f"buyers {_buyers(sig.get('delta_ratio', 0.0))}"]
    elif phase == 'C':
        reasons = ["new high on selling", f"buyers {_buyers(sig.get('flow_divergence', 0.0))}/5h",
                   f"OI {_pct(sig.get('oi_change_3h', 0.0))}/3h", f"fund {_pct(sig.get('funding_rate', 0.0), 3)}"]
    elif phase == 'D':
        reasons = ["below lower BB", f"sellers {_buyers(-sig.get('delta_ratio', 0.0))}",
                   f"OI {_pct(sig.get('oi_change_1h', 0.0))}/1h new shorts"]
    elif phase == 'F':
        reasons = ["above upper BB", f"buyers {_buyers(sig.get('delta_ratio', 0.0))}",
                   f"OI {_pct(sig.get('oi_change_1h', 0.0))}/1h new longs"]
    return reasons + context_parts(sig)


def context_parts(sig: Dict) -> List[str]:
    """Order-flow / positioning context shared by cards and tables."""
    parts: List[str] = []
    w = sig.get('whales') or {}
    if w.get('buys') or w.get('sells'):
        net = w['buy_usd'] - w['sell_usd']
        levels = f" ate {w['max_levels']}lv" if w.get('max_levels', 0) > 2 else ''
        parts.append(f"whales {'+' if net >= 0 else '-'}{_usd(abs(net))} ({w['buys']}↑ {w['sells']}↓){levels}")
    if sig.get('cluster'):
        parts.append("algo " + ("buying" if sig['cluster'] > 0 else "selling"))
    spot, perp = sig.get('spot_delta_1h'), sig.get('perp_delta_1h')
    if spot is not None and perp:
        parts.append(f"spot {'+' if spot >= 0 else '-'}{_usd(abs(spot))} / perp {'+' if perp >= 0 else '-'}{_usd(abs(perp))} 1h")
    liq_l, liq_s = sig.get('liq_long_5m') or 0.0, sig.get('liq_short_5m') or 0.0
    if liq_l + liq_s >= 10_000:
        parts.append(f"liquidated longs {_usd(liq_l)} / shorts {_usd(liq_s)} 5m")
    if sig.get('depth_imb') is not None:
        parts.append(f"book {sig['depth_imb']:+.0%}")
    if (sig.get('book_eaten') or 0) >= 1:
        parts.append(f"sweep ate {sig['book_eaten']:.1f}x book")
    ratios = [(name, sig.get(key)) for name, key in (('Binance', 'ls_global'), ('top', 'ls_top'), ('Bybit', 'ls_bybit'),
                                                       ('OKX', 'ls_okx')) if sig.get(key)]
    if ratios:
        parts.append("L/S " + ', '.join(f"{name} {value:.2f}" for name, value in ratios))
    if sig.get('hl_longs') or sig.get('hl_shorts'):
        parts.append(f"HL large accounts L {_usd(sig.get('hl_long_usd') or 0)} ({sig.get('hl_longs', 0)}) / "
                     f"S {_usd(sig.get('hl_short_usd') or 0)} ({sig.get('hl_shorts', 0)})")
    if sig.get('cb_premium') is not None:
        parts.append(f"Coinbase {sig['cb_premium'] * 100:+.2f}%")
    if sig.get('coin_trend'):
        parts.append(f"coin 1h trend {'up' if sig['coin_trend'] > 0 else 'down'}")
    if sig.get('trend_w') is not None:
        parts.append(f"weekly EMA {sig['trend_w']:+.1f} sd" +
                     (f", market {sig['breadth_w'] * 100:.0f}% above weekly EMA" if sig.get('breadth_w') is not None else ''))
    if sig.get('mkt_1h') is not None:
        parts.append(f"market 1h {sig['mkt_1h'] * 100:+.2f}%" + (f", BTC {sig['btc_1h'] * 100:+.2f}%" if sig.get('btc_1h') is not None else ''))
    if (sig.get('market_crowd') or 0) >= CONFIG.market.cluster_min:
        parts.append(f"market move: {sig['market_crowd']} coins with the same-side setup in 5m")
    if (sig.get('venues_active') or 0) >= 2 and (sig.get('top_venue_share') or 0) >= 0.8:
        parts.append(f"{sig.get('top_venue') or '?'}-only flow")
    return parts


def _num(v):
    """JSON-safe number (NaN / inf -> None)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _name(symbol: str) -> str:
    return symbol.replace(':USDT', '').replace('/USDT', '')


# ---------------------------------------------------------------------------------------------------- state

SIG_FIELDS = ('rvol_1m', 'rvol_15m', 'price_change_5m', 'oi_change_5m', 'oi_change_1h', 'delta_ratio', 'funding_rate',
              'whale_net_5m', 'liq_long_5m', 'liq_short_5m', 'top_venue', 'top_venue_share', 'ml_score', 'long_score',
              'short_score', 'p_edge', 'spot_delta_1h', 'perp_delta_1h', 'depth_imb', 'top_ratio', 'regime',
              'ls_global', 'ls_top', 'ls_bybit', 'ls_okx', 'hl_long_usd', 'hl_short_usd', 'hl_net_usd', 'cb_premium')


def _sig_view(sig: Dict) -> Dict:
    out = {}
    for k in SIG_FIELDS:
        v = sig.get(k)
        out[k] = v if isinstance(v, str) else _num(v)
    out['phases'] = list(sig.get('active_phases') or [])
    return out


def _anchor_view(anchor: Optional[Dict]) -> Optional[Dict]:
    if not anchor:
        return None
    return {k: (v if isinstance(v, str) else _num(v)) for k, v in anchor.items()}


def sizing_view(levels: Optional[Dict], direction: int, funding_8h: Optional[float]) -> Optional[Dict]:
    """
    Sizing facts of an entry for a manual trader (CONFIG.risk): the stop distance, the highest isolated leverage whose
    liquidation stays liq_stop_margin x the stop distance away, the funding the position pays (+) or receives (-) per
    8h at the current rate, and, with an account size configured, the notional and margin for risk_pct of it.
    """
    if not levels or not levels.get('entry') or levels.get('sl') is None or not direction:
        return None
    from strategies.geometry import cost_of
    cfg = CONFIG.risk
    entry, sl = float(levels['entry']), float(levels['sl'])
    stop_frac = abs(entry - sl) / entry
    if stop_frac <= 0:
        return None
    # isolated margin: liquidation about (1/L - maintenance) from the entry
    max_lev = 1.0 / (cfg.liq_stop_margin * stop_frac + CONFIG.zones.liq_maintenance)
    out = {'stop_pct': stop_frac, 'max_leverage': max(1.0, math.floor(max_lev)),
           'funding_8h': (direction * funding_8h) if funding_8h is not None else None}
    if cfg.account_usd > 0:
        risk_usd = cfg.account_usd * cfg.risk_pct / 100
        notional = risk_usd / (stop_frac + cost_of(entry) / entry)
        out.update(risk_usd=risk_usd, notional_usd=notional, margin_usd=notional / out['max_leverage'])
    return out


def fib_view(plan: Dict, levels: Optional[Dict], direction: int) -> Optional[Dict]:
    """
    The Fibonacci grid of a leg card for the chart: the impulse A -> B (with its times), the retracements 0.5 / 0.618
    / 0.705 / 0.786 (the OTE band 0.62-0.79), and after the entry the trend-based extensions from the pullback's
    extreme C (1.0 / 1.2 / 1.272 / 1.618).
    """
    anchor = (plan or {}).get('anchor') or {}
    if anchor.get('type') != 'leg' or anchor.get('start') is None or anchor.get('end') is None:
        return None
    a, b = float(anchor['start']), float(anchor['end'])
    leg = b - a
    out = {'a': a, 'b': b, 'a_ts': anchor.get('start_ts'), 'b_ts': anchor.get('end_ts'),
           'retr': [[r, b - r * leg] for r in (0.5, 0.618, 0.705, 0.786)]}
    c = (levels or {}).get('extreme')
    if c is not None:
        out['c'] = float(c)
        out['ext'] = [[k, float(c) + k * leg] for k in CONFIG.levels.continuation_targets]
    return out


def card_view(s, now: float) -> Dict:
    plan = s.plan or {}
    lv = s.levels or {}
    price = s.last_price
    dist = None
    if plan and price and not s.entered_at and not s.finished:
        lo, hi = plan['zone_lo'], plan['zone_hi']
        if not lo <= price <= hi:
            edge = hi if price > hi else lo
            dist = edge / price - 1
    return {
        'id': f"{s.symbol}|{s.group_key}", 'symbol': s.symbol, 'name': _name(s.symbol), 'setup': s.group_key,
        'strategy': SETUPS.get(s.group_key, ('', 0))[0],
        'direction': s.direction, 'mode': s.mode, 'status': s.status, 'created': s.created,
        'price_at_signal': _num(s.price_at_signal), 'price': _num(price), 'finished': s.finished,
        'finished_at': s.finished_at, 'finish_reason': s.finish_reason, 'entered_at': s.entered_at,
        'zone': [_num(plan.get('zone_lo')), _num(plan.get('zone_hi'))] if plan else None,
        'zone_src': plan.get('zone_src'), 'dist_to_zone': _num(dist),
        'targets': [_num(t) for t in plan.get('targets', [])], 'target_src': plan.get('target_src', []),
        # The plan's anchor (a leg / a level / a range), its structure and entry timeframes
        'anchor': _anchor_view(plan.get('anchor')), 'tf': plan.get('tf'),
        'fib': fib_view(plan, lv, s.direction),
        'trigger_minutes': plan.get('trigger_minutes'),
        # a method without profit targets (Turtles / Connors / ORB / Bollinger's live band, plan no_tp): its TP1-3 are
        # 100 / 200 / 300 R placeholders the lifecycle never reaches - shown as none (a short's came out negative)
        'levels': {k: (None if plan.get('no_tp') and k in ('tp1', 'tp2', 'tp3') else
                       v if isinstance(v, str) else _num(v)) for k, v in lv.items()} if lv else None,
        'sizing': sizing_view(lv, s.direction, s.sig.get('funding_rate')) if lv else None,
        'r_now': _num(s.r_now), 'best_target': s.best_target, 'final_r': _num(s.final_r),
        'vetoed_triggers': s.vetoed_triggers, 'veto_log': list(s.veto_log), 'veto_notes': list(s.veto_notes), 'of_confirm': s.of_confirm,
        'confirms': s.confirms, 'required': list(confirm.required(s.mode)), 'crowd': s.sig.get('market_crowd'),
        'why': explain(s.group_key, s.sig), 'sig': _sig_view(s.sig),
    }


def _anomaly_effect(label: str):
    from journal import ANOMALY_EFFECT
    e = ANOMALY_EFFECT.get(label)
    return {'x': round(e[0], 2), 'n': e[1]} if e else None


def build_state(scanner) -> Dict:
    now = time.time()
    book = scanner.book
    cards = [card_view(s, now) for s in book.signals_view(now)]
    forming = []
    for sym, sig in book.watchlist:
        bull = sig.get('alert_type') == 'LONG'
        phases = [{'phase': p, 'name': PHASE_NAMES[p], 'score': sig.get(f'phase_{p.lower()}_score', 0),
                   'max': PHASE_MAX[p]} for p in (LONG_PHASES if bull else SHORT_PHASES) if sig.get(f'phase_{p.lower()}_score', 0)]
        forming.append({'symbol': sym, 'name': _name(sym), 'direction': 1 if bull else -1, 'phases': phases,
                        'why': context_parts(sig), 'sig': _sig_view(sig)})
    vetoed = [{'symbol': sym, 'name': _name(sym), 'setup': gk, 'reason': reason, 'sig': _sig_view(sig)}
              for sym, gk, reason, sig in book.vetoed]
    anomalies = [{'symbol': a.symbol, 'name': _name(a.symbol), 'label': a.group_key, 'first_seen': a.first_seen,
                  'last_seen': a.last_seen, 'hits': a.hits, 'sig': _sig_view(a.sig), 'why': context_parts(a.sig),
                  'peak': {k: _num(v) for k, v in a.peak.items()},
                  'rules': [k[3:] for k, v in a.sig.items() if k.startswith('t0_') and v],
                  'effect': _anomaly_effect(a.group_key)}
                 for a in book.anomalies_view()]
    venues = {}
    for venue, st in scanner.fetcher.venue_status().items():
        venues[venue] = {k: (v if isinstance(v, (str, bool)) else _num(v)) for k, v in st.items()
                         if isinstance(v, (int, float, str, bool))}
    results, r_list = book.session_results, book.session_r
    return {
        'ts': now,
        'status': scanner._warmup_status(),
        'market': scanner._market_context(),
        'ml': scanner._ml_status(),
        'venues': venues,
        'timing': {'scan': scanner.last_scan_sec, 'heavy': scanner.last_heavy_sec, 'tier0': scanner.last_tier0_sec},
        'symbols': len(scanner.market_data), 'hot': len(scanner._hot),
        'cards': cards, 'forming': forming, 'vetoed': vetoed, 'anomalies': anomalies,
        'pools': scanner.pools.view(),
        'archive_negative': list(CONFIG.strategies.archive_negative),
        'pumps': [dict(r, name=_name(r['symbol'])) for r in pumps.monitor(scanner.market_data, now * 1000,
                                                                          scanner._pump_cache)],
        'session': {'results': dict(results), 'r': [_num(r) for r in r_list]},
        'logic_version': CONFIG.journal.logic_version,
    }


# ---------------------------------------------------------------------------------------------------- journal queries

class JournalReader:
    """Read-only journal access for the page (own connection, worker thread) with the universe baseline cached."""

    BASELINE_TTL = 600

    def __init__(self, path: str = CONFIG.journal.db_path):
        self.path = path
        self._baseline = None
        self._baseline_at = 0.0

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _universe(self, conn):
        from stats import UniverseBaseline
        if self._baseline is None or time.time() - self._baseline_at > self.BASELINE_TTL:
            self._baseline, self._baseline_at = UniverseBaseline(conn), time.time()
        return self._baseline

    def _row(self, r: sqlite3.Row, base) -> Dict:
        keys = r.keys()
        out = {k: r[k] for k in ('id', 'ts_ms', 'symbol', 'kind', 'group_key', 'direction', 'price', 'vetoed',
                                 'rvol_1m', 'price_change_5m', 'oi_change_5m', 'whale_net_5m', 'mfe_4h', 'mae_4h')}
        for k in ('entry', 'sl', 'tp1', 'tp2', 'tp3', 'outcome', 'r_tp1', 'r_tp2', 'rr_tp1', 'reason', 'tp1_src',
                  'tp2_src', 'tp3_src', 'sl_src', 'zone_src', 'setup_ts_ms', 'of_confirm', 'confirms', 'liq_long_5m',
                  'liq_short_5m', 'top_venue', 'ml_score', 'regime', 'p_edge', 'entry_fill', 'filled', 'logic_version'):
            out[k] = r[k] if k in keys else None
        out['name'] = _name(r['symbol'])
        out['confirms'] = orjson.loads(out['confirms']) if out.get('confirms') else None
        d = r['direction'] or 0
        for label, minutes in HORIZONS.items():
            ret = r[f'ret_{label}']
            out[f'ret_{label}'] = ret
            m = base.ret(r['ts_ms'], minutes) if (base and ret is not None) else None
            out[f'edge_{label}'] = d * (ret - m) if (d and m is not None) else None
        return out

    def history(self, kind: str, hours: float, symbol: Optional[str] = None, limit: int = 600) -> List[Dict]:
        since = int((time.time() - hours * 3600) * 1000)
        # All logic versions: anomaly labels did not change with the trade geometry, and the page shows each row's
        # own levels (stats.py keeps comparing only rows of the current version)
        sql = "SELECT * FROM signals WHERE ts_ms >= ?"
        args: list = [since]
        if kind != 'all':
            sql += " AND kind = ?"
            args.append(kind)
        if symbol:
            sql += " AND symbol = ?"
            args.append(symbol)
        sql += " ORDER BY ts_ms DESC LIMIT ?"
        args.append(limit)
        conn = self._conn()
        try:
            rows = conn.execute(sql, args).fetchall()
            base = self._universe(conn)
            return [self._row(r, base) for r in rows]
        finally:
            conn.close()

    def anomaly_stats(self, hours: float) -> List[Dict]:
        rows = self.history('anomaly', hours, limit=20000)
        groups: Dict[str, List[Dict]] = {}
        for r in rows:
            groups.setdefault(r['group_key'], []).append(r)
        out = []
        for label, members in groups.items():
            d = members[0]['direction'] or 0
            item = {'label': label, 'n': len(members), 'directional': bool(d)}
            for h in HORIZONS:
                vals = [r[f'ret_{h}'] * (r['direction'] or 1) if r['direction'] else abs(r[f'ret_{h}'])
                        for r in members if r[f'ret_{h}'] is not None]
                edges = [r[f'edge_{h}'] for r in members if r[f'edge_{h}'] is not None]
                item[f'n_{h}'] = len(vals)
                item[f'avg_{h}'] = statistics.fmean(vals) if vals else None
                item[f'hit_{h}'] = (sum(v > 0 for v in vals) / len(vals)) if (vals and d) else None
                item[f'edge_{h}'] = statistics.fmean(edges) if edges else None
            out.append(item)
        out.sort(key=lambda i: -i['n'])
        return out

    def stats_html(self, days: Optional[float]) -> str:
        from rich.console import Console
        from stats import report
        console = Console(record=True, file=io.StringIO(), width=180, color_system='truecolor')
        report(console, self.path, days=days, last=0)
        return console.export_html(inline_styles=True, code_format='<pre class="rich">{code}</pre>')


# ---------------------------------------------------------------------------------------------------- server

def untaken_densities(snapshots, candles_15m, price, hours: int = 24, multiple: float = 2.5,
                      presence: float = 0.6, keep: int = 4):
    """
    Order-book densities that STAYED and price has not reached since they appeared: per snapshot of the last `hours`,
    the price buckets holding >= `multiple` x that snapshot's median bucket; a bucket that did so in >= `presence` of
    the snapshots since it first did (at least 6) is a density; untaken = no 15m candle traded through it since. The
    `keep` largest per side: [{price, side +1 bid / -1 ask, usd, since_ms}] (what the chart's heat should point at,
    not every bucket shaded alike).
    """
    import statistics
    if not snapshots or not price:
        return []
    cutoff = snapshots[-1][0] - hours * 3_600_000
    recent = [s for s in snapshots if s[0] >= cutoff]
    seen = {}                              # price -> [first ms, hits, usd sum, side sum, snapshots since first]
    for ts, cells in recent:
        if not cells:
            continue
        med = statistics.median(abs(v) for _, v in cells) or 0.0
        big = {round(p, 10): v for p, v in cells if med and abs(v) >= multiple * med}
        for p in list(seen):
            seen[p][4] += 1
        for p, v in big.items():
            row = seen.setdefault(p, [ts, 0, 0.0, 0, 0])
            if row[4] == 0:
                row[4] = 1
            row[1] += 1
            row[2] += abs(v)
            row[3] += 1 if v > 0 else -1
    out = []
    for p, (first, hits, usd, side, n) in seen.items():
        if hits < 6 or hits < presence * n:
            continue
        s = 1 if side > 0 else -1
        after = [c for c in candles_15m if c[0] + 900_000 > first]
        if s > 0 and (p >= price or any(c[3] <= p for c in after)):
            continue                       # a bid density price already reached (or above price: not support)
        if s < 0 and (p <= price or any(c[2] >= p for c in after)):
            continue
        out.append({'price': p, 'side': s, 'usd': usd / hits, 'since_ms': int(first)})
    bids = sorted((d for d in out if d['side'] > 0), key=lambda d: -d['usd'])[:keep]
    asks = sorted((d for d in out if d['side'] < 0), key=lambda d: -d['usd'])[:keep]
    return bids + asks


class WebUI:
    def __init__(self, scanner):
        self.scanner = scanner
        self.reader = JournalReader()
        self.clients: set = set()
        self._runner: Optional[web.AppRunner] = None
        self._last_state: bytes = b'{}'
        self._sending: set = set()

    @property
    def url(self) -> str:
        return f"http://{CONFIG.web.host}:{CONFIG.web.port}/"

    async def start(self):
        app = web.Application()
        app.router.add_get('/', self._index)
        app.router.add_get('/ws', self._ws)
        app.router.add_get('/api/coin', self._coin)
        app.router.add_get('/api/history', self._history)
        app.router.add_get('/api/anomaly_stats', self._anomaly_stats)
        app.router.add_get('/api/stats', self._stats)
        app.router.add_get('/api/debug', self._debug)
        app.router.add_static('/static/', WEB_DIR)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, CONFIG.web.host, CONFIG.web.port).start()
        logger.info(f"Web dashboard: {self.url}")
        if CONFIG.web.open_browser:
            try:
                webbrowser.open(self.url)
            except Exception as e:
                logger.debug(f"Could not open the browser: {e}")

    async def stop(self):
        for ws in list(self.clients):
            await ws.close()
        if self._runner is not None:
            await self._runner.cleanup()

    def publish(self):
        """Called after every scan: serialize once, push to every open page (a slow page skips updates)."""
        if not self.clients:
            return
        try:
            self._last_state = orjson.dumps(build_state(self.scanner), default=str)
        except Exception as e:
            logger.error(f"Web state build failed: {e}", exc_info=True)
            return
        text = self._last_state.decode()
        for ws in list(self.clients):
            if ws in self._sending or ws.closed:
                continue
            task = asyncio.create_task(self._send(ws, text))
            self._sending.add(ws)
            task.add_done_callback(lambda _t, w=ws: self._sending.discard(w))

    async def _send(self, ws, text: str):
        try:
            await asyncio.wait_for(ws.send_str(text), timeout=5)
        except Exception:
            self.clients.discard(ws)

    # ---------------------------------------------------------------- handlers

    async def _index(self, request):
        return web.FileResponse(os.path.join(WEB_DIR, 'index.html'), headers={'Cache-Control': 'no-cache'})

    async def _ws(self, request):
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self.clients.add(ws)
        try:
            await ws.send_str(orjson.dumps(build_state(self.scanner), default=str).decode())
            async for msg in ws:
                if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        except (ConnectionResetError, aiohttp.ClientConnectionResetError):
            pass                                  # the tab closed / reloaded while the state was sent: not an error
        finally:
            self.clients.discard(ws)
        return ws

    @staticmethod
    def _json(data) -> web.Response:
        return web.Response(body=orjson.dumps(data, default=str, option=orjson.OPT_SERIALIZE_NUMPY),
                            content_type='application/json')

    async def _coin(self, request):
        symbol = request.query.get('symbol', '')
        if symbol in self.scanner.market_data:
            detail = await self.scanner.coin_detail(symbol)
        else:
            # A coin from the journal that left the universe: candles from REST, no level map
            detail = await self.scanner.fetcher.chart_candles(symbol)
            if detail is None:
                return self._json({'error': f'no data for {symbol}'})
        detail['journal'] = await asyncio.to_thread(self.reader.history, 'all', 48, symbol, 300)
        # the order-book heatmap older than the ~4h in memory, from the recorder's depth files (4 days, 10-min steps)
        try:
            import time as _time
            from config import CONFIG
            from recorder import heat_history
            live = detail.get('heatmap') or {'step': 0.0, 'snapshots': []}
            first = live['snapshots'][0][0] if live['snapshots'] else int(_time.time() * 1000)
            past = await asyncio.to_thread(heat_history, CONFIG.recorder.root, symbol, first - 4 * 86_400_000, first,
                                           live['step'] or None)
            if past['snapshots']:
                if live['step']:
                    # the recorded bands on the live grid's step (both are 0.1% of price)
                    past['snapshots'] = [[t, [[round(p / live['step']) * live['step'], v] for p, v in lv]]
                                         for t, lv in past['snapshots']]
                detail['heatmap'] = {'step': live['step'] or past['step'],
                                     'snapshots': past['snapshots'] + live['snapshots']}
        except Exception as e:
            logging.getLogger(__name__).warning(f"Heatmap history of {symbol}: {type(e).__name__} {e}")
        try:
            detail['densities'] = untaken_densities((detail.get('heatmap') or {}).get('snapshots') or [],
                                                    detail.get('candles_15m') or [], detail.get('price'))
        except Exception as e:
            logging.getLogger(__name__).warning(f"Densities of {symbol}: {type(e).__name__} {e}")
        return self._json(detail)

    async def _history(self, request):
        kind = request.query.get('kind', 'card')
        if kind not in ('card', 'anomaly', 'entry', 'structured', 'setup', 'all'):
            kind = 'card'
        hours = float(request.query.get('hours', 24))
        symbol = request.query.get('symbol') or None
        return self._json(await asyncio.to_thread(self.reader.history, kind, hours, symbol))

    async def _debug(self, request):
        """Internal state of one coin (verification against the exchanges' own REST numbers)."""
        from flow import BUY, LIQ_LONG, LIQ_SHORT, SELL
        symbol = request.query.get('symbol', '')
        f = self.scanner.fetcher
        md = self.scanner.market_data.get(symbol)
        if md is None:
            return self._json({'error': f'unknown symbol {symbol}'})
        now = time.time()
        row = f.flow.rows.get(symbol)
        flows = {}
        for venue, vf in f.flow.venues.items():
            if row is None:
                continue
            flows[venue] = {w: {name: float(vf.window(field, sec, int(now))[row])
                                for name, field in (('buy', BUY), ('sell', SELL), ('liq_long', LIQ_LONG),
                                                    ('liq_short', LIQ_SHORT))}
                            for w, sec in (('60s', 60), ('5m', 300))}
            # The last 5 CLOSED minutes, [start, start+60s) each: comparable 1:1 with the venues' 1m candles
            last_min = int(now) // 60 * 60
            flows[venue]['minutes'] = [
                [(last_min - 60 * k) * 1000,
                 float(vf.range_sum(BUY, last_min - 60 * k, last_min - 60 * (k - 1), int(now))[row]),
                 float(vf.range_sum(SELL, last_min - 60 * k, last_min - 60 * (k - 1), int(now))[row])]
                for k in range(5, 0, -1)]
        derivs = {v: {'oi_usd': s.oi_usd, 'funding_8h': s.funding_8h, 'mark': s.mark,
                      'age_sec': (now * 1000 - s.ts) / 1000 if s.ts else None, 'samples': len(s.samples),
                      'oi_5m_ago': next((x[1] for x in reversed(s.samples) if x[0] <= now * 1000 - 300_000), None)}
                  for v, s in f.venue_derivs.get(symbol, {}).items()}
        whales, notable = f.whales.thresholds(symbol)
        hist = f.whales.hist.get(symbol)
        mapping = {v: {'native': m.native, 'multiplier': m.multiplier, 'contract_value': m.contract_value,
                       'verified': m.verified} for v, m in f.symbol_map.by_key.get(symbol, {}).items()}
        return self._json({
            'symbol': symbol, 'price': self.scanner._price_of(symbol), 'mapping': mapping,
            'flows': flows, 'derivs': derivs, 'deriv_snapshot': f.deriv_snapshot(symbol),
            'binance_oi_samples': [list(x) for x in list(md.oi_samples)[-6:]], 'tier0': md.tier0,
            # stream histories (seeded from REST at start-up): sizes and spans in minutes
            'history': {'oi_samples': len(md.oi_samples),
                        'oi_span_min': (md.oi_samples[-1][0] - md.oi_samples[0][0]) / 60_000 if len(md.oi_samples) > 1 else 0,
                        'minute_klines': len(md.minute_klines), 'spot_minute_klines': len(md.spot_minute_klines),
                        'ticker_samples': len(md.ticker_samples)},
            'whale_size': whales, 'notable_size': notable, 'hist_total': float(hist.sum()) if hist is not None else 0,
            'whale_records': [list(r) for r in list(f.whales.whales.get(symbol, ()))[-200:]],
            'whale_flow_5m': f.whales.flow(symbol, 300), 'cluster': f.whales.cluster(symbol),
            'sweeps_seen_total': f.whales.sweeps_seen,
            'liq_events': [list(e) for e in list(md.liq_events)[-25:]],
            'depth': f.depth.metrics(symbol), 'book_levels': (len(f.depth.books[symbol].bids), len(f.depth.books[symbol].asks))
            if symbol in f.depth.books else None,
            'funding_rate': md.funding_rate, 'mark': md.mark_price, 'index': md.index_price,
        })

    async def _anomaly_stats(self, request):
        hours = float(request.query.get('hours', 24))
        return self._json(await asyncio.to_thread(self.reader.anomaly_stats, hours))

    async def _stats(self, request):
        days = request.query.get('days')
        html = await asyncio.to_thread(self.reader.stats_html, float(days) if days else None)
        return web.Response(text=html, content_type='text/html')
