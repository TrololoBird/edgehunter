"""
Per-strategy coin pools (CONFIG.pools): every strategy trades only its own coins. See PoolsConfig for the rule and
the measurement behind the automatic exclusion. Rebuilt hourly off the loop by Scanner.pools_loop.
"""
import bisect
import time
from typing import Dict, List, Optional, Set, Tuple

from config import CONFIG
from sectors import sector_of

MAJORS = ('BTC', 'ETH', 'SOL', 'XRP', 'BNB')


def coin_class(symbol: str, rank: int) -> str:
    base = symbol.split('/')[0]
    if base in MAJORS:
        return 'major'
    return 'large' if rank <= 30 else 'mid' if rank <= 80 else 'small'


def atr_pct_1h(h1: List[List[float]]) -> Optional[float]:
    if not h1 or len(h1) < 15:
        return None
    rows = h1[-15:]
    trs = [max(r[2] - r[3], abs(r[2] - p[4]), abs(r[3] - p[4])) for p, r in zip(rows, rows[1:])]
    return sum(trs) / len(trs) / rows[-1][4] * 100 if rows[-1][4] else None


class Pools:
    def __init__(self):
        self.members: Dict[str, Set[str]] = {}
        self.excluded: Dict[str, Dict[str, Tuple[int, float]]] = {}
        self.info: Dict[str, Dict] = {}
        self.updated = 0.0
        self.small_of = lambda: set()               # eng-99: the scanner points it at fetcher.small_caps

    def allows(self, strategy: str, symbol: str) -> bool:
        """True when pools are off, not built yet, or the coin is in the strategy's pool."""
        if symbol in self.small_of():
            # eng-99: the small-cap tier trades only the small-cap strategies
            return strategy in CONFIG.exchange.smallcap_strategies
        if not CONFIG.pools.enabled or not self.updated:
            return True
        if symbol.split('/')[0] in CONFIG.exchange.pinned_bases:
            return True                          # pinned coins trade every strategy (CONFIG.exchange.pinned_bases)
        pool = self.members.get(strategy)
        if pool is None:
            # no rule for this strategy: the whole universe minus the coins its journal proved losing
            return symbol not in self.excluded.get(strategy, {})
        return symbol in pool

    def rebuild(self, markets: Dict, sectors_map: Dict[str, str],
                entries: List[Tuple[str, str, int, int, float]],
                market_volumes: Optional[List[float]] = None) -> None:
        """
        entries: (strategy, symbol, ts_ms, direction, net R) of the journal's replayed, non-vetoed entries.
        market_volumes: the 24h quote volume of EVERY Binance USDT perpetual (eng-59): a coin's class is its rank in
        the whole market - ranked within the 70-coin universe, 'mid = rank <= 80' meant every coin.
        """
        from journal import block_of, proven_negative
        cfg = CONFIG.pools
        ranked = sorted(markets.items(), key=lambda kv: -(kv[1].quote_volume_24h or 0.0))
        desc = sorted((-v for v in market_volumes or [] if v), )
        info = {}
        for local_rank, (sym, md) in enumerate(ranked, 1):
            vol = md.quote_volume_24h or 0.0
            rank = bisect.bisect_left(desc, -vol) + 1 if desc else local_rank
            info[sym] = {'class': coin_class(sym, rank), 'sector': sector_of(sym, sectors_map) or 'other',
                         'atr_1h_pct': atr_pct_1h(md.h1), 'volume_24h': vol, 'rank': rank}
        # eng-59: a coin leaves a strategy's pool only when its entries there are PROVEN negative - 4h blocks of one
        # direction resampled together, Benjamini-Hochberg over every coin x strategy pair (journal.proven_negative,
        # the rule the regime mutes and confirmation promotions use). The old cut (mean <= -0.3R over 8 entries)
        # dropped coins by chance: at ~1R spread per trade the mean of 8 has a standard error of ~0.35R.
        groups: Dict[tuple, Dict[tuple, List[float]]] = {}
        for strategy, symbol, ts_ms, direction, r in entries:
            if r is not None:
                groups.setdefault((strategy, symbol), {}).setdefault(block_of(int(ts_ms), int(direction or 0)), []).append(float(r))
        stats, proven = proven_negative(groups, cfg.min_blocks, CONFIG.ml.rule_fdr, seed=13)
        bad: Dict[str, Dict[str, Tuple[int, float]]] = {}
        for strategy, symbol in proven:
            values = [v for b in groups[(strategy, symbol)].values() for v in b]
            bad.setdefault(strategy, {})[symbol] = (stats[(strategy, symbol)][0], sum(values) / len(values))
        members: Dict[str, Set[str]] = {}
        pinned = [s for s in info if s.split('/')[0] in CONFIG.exchange.pinned_bases]
        for strategy, classes, excl_sectors, min_atr, order in cfg.rules:
            allowed = None if classes == 'all' else set(c.strip() for c in classes.split(',') if c.strip())
            excl = set(x.strip() for x in excl_sectors.split(',') if x.strip())
            pool = list(pinned)
            # the rest of the pool in the order the method wants its coins: 'volume' (liquid, two-sided auctions:
            # value area, mean reversion, absorption), 'volatility' (1h ATR %: trend / breakout methods need range
            # expansion - the Turtles took every market with movement), 'alts' (outside the 30 most traded: the
            # supply / demand and liquidity-run systems their authors traded on altcoins)
            if order == 'volatility':
                candidates = sorted(ranked, key=lambda kv: -(info[kv[0]]['atr_1h_pct'] or 0.0))
            elif order == 'alts':
                candidates = [kv for kv in ranked if info[kv[0]]['rank'] > 30]
            else:
                candidates = ranked
            for sym, _ in candidates:
                if sym in pool:
                    continue
                c = info[sym]
                if allowed is not None and c['class'] not in allowed:
                    continue
                if c['sector'] in excl or sym in bad.get(strategy, {}):
                    continue
                if min_atr and (c['atr_1h_pct'] is None or c['atr_1h_pct'] < min_atr):
                    continue
                pool.append(sym)
                if len(pool) >= cfg.size + len(pinned):
                    break
            members[strategy] = set(pool)
        self.members, self.excluded, self.info, self.updated = members, bad, info, time.time()

    def view(self) -> Dict:
        """For the dashboard: each strategy's pool and the coins excluded by their journaled results."""
        name = lambda s: s.split('/')[0]
        return {'updated': self.updated,
                'pools': {k: sorted((name(s) for s in v), key=lambda n: n) for k, v in self.members.items()},
                'excluded': {k: {name(s): {'blocks': n, 'r': round(r, 3)} for s, (n, r) in v.items()}
                             for k, v in self.excluded.items()},
                'classes': {name(s): {'class': i['class'], 'sector': i['sector']} for s, i in self.info.items()}}
