"""
Event risk from Binance's own public data (eng-53; Compass "7 phases" review: scheduled / announced events are the
best-documented driver of dumps):
- the Monitoring Tag (Binance's delisting watch list): the spot product list carries tags['Monitoring'] - live after
  a tag, AVA -4.9%, SCR -7.5%, NFP -12%, WAN -34% within minutes / an hour (BeInCrypto, cryptorank);
- a scheduled delisting of the perpetual: futures exchangeInfo sets the contract's deliveryDate to the removal time
  (an ordinary perpetual carries 2100-12-25) - after Binance's delisting announcement of 2026-04-09: FUN -27.9%,
  MDT -22.8%, FIO -20.5% within minutes.
Token unlocks (Keyrock: 90% of 16,000+ unlocks pressure the price for 30 days) need an external calendar: not here.
Read every hour off the loop; a failed read keeps the last known state.
"""
import json
import logging
import time
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PRODUCTS_URL = 'https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-products?includeEtf=true'
FAPI_INFO_URL = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
DELIVERY_HORIZON_MS = 90 * 86400 * 1000      # a perpetual delivering within 90 days is being delisted


def _get(url: str):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


class EventRisk:
    def __init__(self):
        self.by_base: Dict[str, str] = {}        # base asset (BTC, PEPE ...) -> 'monitoring' / 'delisting <date>'
        self.updated = 0.0

    @staticmethod
    def _base(symbol: str) -> str:
        base = symbol.split('/')[0]
        for prefix in ('1000000', '10000', '1000', '1M'):
            if base.startswith(prefix) and len(base) > len(prefix):
                return base[len(prefix):]
        return base

    def refresh(self) -> None:
        """Blocking (run in a thread): both sources; each keeps its last state when its read fails."""
        found: Dict[str, str] = {}
        ok = 0
        try:
            for p in _get(PRODUCTS_URL).get('data') or []:
                if 'Monitoring' in (p.get('tags') or []) and p.get('b'):
                    found[p['b']] = 'monitoring'
            ok += 1
        except Exception as e:
            logger.info(f"Event risk: Binance product tags failed ({e!r}), kept the last state")
            found.update({b: r for b, r in self.by_base.items() if r == 'monitoring'})
        try:
            now = time.time() * 1000
            for s in _get(FAPI_INFO_URL).get('symbols') or []:
                due = int(s.get('deliveryDate') or 0)
                if s.get('contractType') == 'PERPETUAL' and now < due < now + DELIVERY_HORIZON_MS:
                    day = time.strftime('%Y-%m-%d', time.gmtime(due / 1000))
                    found[self._base(s['baseAsset'])] = f'delisting {day}'
            ok += 1
        except Exception as e:
            logger.info(f"Event risk: futures exchangeInfo failed ({e!r}), kept the last state")
            found.update({b: r for b, r in self.by_base.items() if r.startswith('delisting')})
        self.by_base = found
        if ok:
            self.updated = time.time()
        logger.info(f"Event risk: {sum(1 for r in found.values() if r == 'monitoring')} coins with the Monitoring Tag, "
                    f"{sum(1 for r in found.values() if r.startswith('delisting'))} perpetuals being delisted")

    def of(self, symbol: str) -> Optional[str]:
        return self.by_base.get(self._base(symbol))
