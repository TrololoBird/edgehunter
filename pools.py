"""
Per-strategy coin pools (CONFIG.pools): every strategy trades only its own coins. See PoolsConfig for the rule and
the measurement behind the automatic exclusion. Rebuilt hourly off the loop by Scanner.pools_loop.
"""
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

    def allows(self, strategy: str, symbol: str) -> bool:
        """True when pools are off, not built yet, or the coin is in the strategy's pool."""
        if not CONFIG.pools.enabled or not self.updated:
            return True
        pool = self.members.get(strategy)
        return pool is None or symbol in pool

    def rebuild(self, markets: Dict, sectors_map: Dict[str, str],
                coin_results: List[Tuple[str, str, int, float]]) -> None:
        cfg = CONFIG.pools
        ranked = sorted(markets.items(), key=lambda kv: -(kv[1].quote_volume_24h or 0.0))
        info = {}
        for rank, (sym, md) in enumerate(ranked, 1):
            info[sym] = {'class': coin_class(sym, rank), 'sector': sector_of(sym, sectors_map) or 'other',
                         'atr_1h_pct': atr_pct_1h(md.h1), 'volume_24h': md.quote_volume_24h or 0.0, 'rank': rank}
        bad: Dict[str, Dict[str, Tuple[int, float]]] = {}
        for strategy, symbol, n, r in coin_results:
            if n >= cfg.min_entries and r is not None and r <= cfg.exclude_below_r:
                bad.setdefault(strategy, {})[symbol] = (int(n), float(r))
        members: Dict[str, Set[str]] = {}
        for strategy, classes, excl_sectors, min_atr in cfg.rules:
            allowed = None if classes == 'all' else set(c.strip() for c in classes.split(',') if c.strip())
            excl = set(x.strip() for x in excl_sectors.split(',') if x.strip())
            pool = []
            for sym, _ in ranked:
                c = info[sym]
                if allowed is not None and c['class'] not in allowed:
                    continue
                if c['sector'] in excl or sym in bad.get(strategy, {}):
                    continue
                if min_atr and (c['atr_1h_pct'] is None or c['atr_1h_pct'] < min_atr):
                    continue
                pool.append(sym)
                if len(pool) >= cfg.size:
                    break
            members[strategy] = set(pool)
        self.members, self.excluded, self.info, self.updated = members, bad, info, time.time()

    def view(self) -> Dict:
        """For the dashboard: each strategy's pool and the coins excluded by their journaled results."""
        name = lambda s: s.split('/')[0]
        return {'updated': self.updated,
                'pools': {k: sorted((name(s) for s in v), key=lambda n: n) for k, v in self.members.items()},
                'excluded': {k: {name(s): {'entries': n, 'r': round(r, 3)} for s, (n, r) in v.items()}
                             for k, v in self.excluded.items()},
                'classes': {name(s): {'class': i['class'], 'sector': i['sector']} for s, i in self.info.items()}}
