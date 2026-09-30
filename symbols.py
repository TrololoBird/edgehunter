"""
Canonical symbols across venues.

The key of every coin is its Binance USD-M futures ccxt symbol (e.g. '1000PEPE/USDT:USDT'), the same key MarketData
uses. Other venues are mapped by base coin: prefixes that scale the unit (1000PEPE, 10000..., 1M..., Hyperliquid's
kPEPE) are split into (coin, multiplier). Order-flow aggregation works in USD notional, which is invariant to the
unit (USD = price x size x contract_value; OKX sizes are contracts of ctVal coins), so multipliers only matter for
comparing prices. A mapping whose per-coin price deviates from Binance by more than venues.max_price_deviation is
dropped (two different tokens sharing a ticker).
"""
import logging
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from config import CONFIG

logger = logging.getLogger(__name__)

_NUMERIC_PREFIX = re.compile(r'^(1000000|100000|10000|1000|100)(?=[A-Z])')


def split_base(base: str, venue: str = '') -> Tuple[str, float]:
    """'1000PEPE' -> ('PEPE', 1000); '1MBABYDOGE' -> ('BABYDOGE', 1e6); Hyperliquid 'kPEPE' -> ('PEPE', 1000)."""
    if not base:
        return base, 1.0
    if venue == 'hyperliquid' and len(base) > 1 and base[0] == 'k' and base[1].isupper():
        return base[1:], 1000.0
    match = _NUMERIC_PREFIX.match(base)
    if match:
        return base[match.end():], float(match.group(1))
    if base.startswith('1M') and len(base) > 2 and base[2].isupper():
        return base[2:], 1e6
    return base.upper(), 1.0


@dataclass
class VenueMarket:
    venue: str
    native: str          # the id used on the venue's websocket (BTCUSDT, BTC-USDT-SWAP, kPEPE, BTC-USD)
    key: str             # canonical key (Binance futures ccxt symbol)
    coin: str
    multiplier: float    # one native price unit = `multiplier` coins
    contract_value: float = 1.0  # coins per unit of the venue's trade size (OKX ctVal), before the multiplier
    spot: bool = False
    verified: bool = False


class SymbolMap:
    def __init__(self):
        self.coin_to_key: Dict[str, str] = {}
        self.key_multiplier: Dict[str, float] = {}
        self.by_venue: Dict[str, Dict[str, VenueMarket]] = {}
        self.by_key: Dict[str, Dict[str, VenueMarket]] = {}
        self.dropped: Dict[Tuple[str, str], str] = {}
        # Every venue's instruments (small dicts: native, base, contract_value), kept after mapping: a universe
        # change maps them again, so coins that join later get their venues too (before, only the start-up
        # universe was ever mapped), and the universe selection can check any candidate's venue coverage
        self._rows: Dict[str, Tuple[List[dict], bool]] = {}
        # (venue, native) whose price was checked against Binance: survives re-mapping
        self._verified: set = set()

    # ------------------------------------------------------------------ building

    def set_universe(self, binance_markets: Dict[str, dict]):
        """binance_markets: canonical key -> its ccxt market (the current universe)."""
        self.coin_to_key.clear()
        self.key_multiplier.clear()
        for key, market in binance_markets.items():
            coin, mult = split_base(market.get('base') or key.split('/')[0])
            self.coin_to_key[coin] = key
            self.key_multiplier[key] = mult
        # Map every loaded venue onto the new universe (price-verified drops stay dropped)
        self.by_venue, self.by_key = {}, {}
        for venue in list(self._rows):
            self._map_venue(venue, log=False)

    def coverage(self, binance_markets: Dict[str, dict]) -> Dict[str, List[str]]:
        """Venues each candidate key would be mapped to (pure: the live mapping is not touched)."""
        coin_to_key = {split_base(m.get('base') or key.split('/')[0])[0]: key for key, m in binance_markets.items()}
        out: Dict[str, List[str]] = {key: [] for key in binance_markets}
        for venue, (markets, _) in self._rows.items():
            for market in markets:
                key = coin_to_key.get(split_base(market['base'], venue)[0])
                if key is not None and (venue, market['native']) not in self.dropped and venue not in out[key]:
                    out[key].append(venue)
        return out

    def _put(self, m: VenueMarket):
        self.by_venue.setdefault(m.venue, {})[m.native] = m
        self.by_key.setdefault(m.key, {})[m.venue] = m

    def add_venue(self, venue: str, markets: Iterable[dict], spot: bool = False):
        """
        Map a venue's ccxt markets onto the universe. Each market dict needs 'native', 'base' and optionally
        'contract_value' (see venues.load_venue_markets). One market per coin per venue: the one whose unit
        multiplier matches Binance's, else the plain (x1) one.
        """
        self._rows[venue] = ([dict(m) for m in markets], spot)
        self._map_venue(venue)

    def _map_venue(self, venue: str, log: bool = True):
        markets, spot = self._rows[venue]
        candidates: Dict[str, List[VenueMarket]] = {}
        for market in markets:
            coin, mult = split_base(market['base'], venue)
            key = self.coin_to_key.get(coin)
            if key is None:
                continue
            candidates.setdefault(coin, []).append(VenueMarket(
                venue=venue, native=market['native'], key=key, coin=coin, multiplier=mult,
                contract_value=float(market.get('contract_value') or 1.0), spot=spot,
                verified=(venue, market['native']) in self._verified,
            ))
        self.by_venue[venue] = {}
        for coin, options in candidates.items():
            target = self.key_multiplier.get(self.coin_to_key[coin], 1.0)
            options.sort(key=lambda m: (m.multiplier != target, m.multiplier != 1.0))
            chosen = options[0]
            if (venue, chosen.native) in self.dropped:
                continue
            self._put(chosen)
        if log:
            logger.info(f"Symbol map: {venue} {len(self.by_venue[venue])} coins mapped onto the universe")

    # ------------------------------------------------------------------ lookups

    def lookup(self, venue: str, native: str) -> Optional[VenueMarket]:
        return self.by_venue.get(venue, {}).get(native)

    def natives(self, venue: str) -> List[str]:
        return list(self.by_venue.get(venue, {}))

    def venues_of(self, key: str) -> List[str]:
        return list(self.by_key.get(key, {}))

    def usd(self, m: VenueMarket, price: float, size: float) -> float:
        return price * size * m.contract_value

    def _deviation(self, m: VenueMarket, venue_price: float, binance_price: float) -> Tuple[float, float, float]:
        per_coin_venue = venue_price / m.multiplier
        per_coin_binance = binance_price / self.key_multiplier.get(m.key, 1.0)
        return abs(per_coin_venue / per_coin_binance - 1), per_coin_venue, per_coin_binance

    def _drop(self, m: VenueMarket):
        self.dropped[(m.venue, m.native)] = m.key
        self.by_venue.get(m.venue, {}).pop(m.native, None)
        self.by_key.get(m.key, {}).pop(m.venue, None)

    def verify_prices(self, venue: str, venue_prices: Dict[str, float], binance_prices: Dict[str, float]) -> List[str]:
        """
        Check every mapping of a venue against Binance before anything is subscribed (one bulk ticker call per venue):
        a per-coin price more than max_price_deviation away means a different token under the same ticker, and the
        mapping is dropped. Returns the dropped natives; the rest are marked verified.
        """
        dropped = []
        for m in list(self.by_venue.get(venue, {}).values()):
            price, reference = venue_prices.get(m.native), binance_prices.get(m.key)
            if not price or not reference:
                continue  # unknown now: the first live trade is checked instead (check_price)
            if self._deviation(m, price, reference)[0] > CONFIG.venues.max_price_deviation:
                self._drop(m)
                dropped.append(m.native)
            else:
                m.verified = True
                self._verified.add((m.venue, m.native))
        return dropped

    def check_price(self, m: VenueMarket, venue_price: float, binance_price: Optional[float]) -> bool:
        """
        Compare the venue's per-coin price with Binance's; drop the mapping on a large deviation (two different
        tokens under one ticker). Returns True while the mapping is (still) valid.
        """
        if m.verified or not binance_price or not venue_price:
            return True
        deviation, per_coin_venue, per_coin_binance = self._deviation(m, venue_price, binance_price)
        if deviation > CONFIG.venues.max_price_deviation:
            if (m.venue, m.native) not in self.dropped:
                # Normally caught by verify_prices at start-up; reaching this means the venue had no ticker then.
                # The check doing its job (a different token under the same ticker): INFO, not a fault
                logger.info(f"Symbol map: dropped {m.venue} {m.native} for {m.key} "
                               f"(price {per_coin_venue:.6g} vs Binance {per_coin_binance:.6g})")
            self._drop(m)
            return False
        m.verified = True
        self._verified.add((m.venue, m.native))
        return True
