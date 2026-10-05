"""
Coin sectors from CoinGecko's public API (no key): a fixed list of broad categories; a coin listed in several gets
the first of them in CATEGORIES order, and a ticker shared by several tokens goes to the one with the biggest cap.
Cached for a day in models/sectors.json. Used by the per-strategy coin pools (`pools.py`) and the stats splits.
"""
import errors
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

CATEGORIES = {
    'layer-1': 'L1', 'layer-2': 'L2', 'meme-token': 'meme', 'decentralized-finance-defi': 'DeFi',
    'artificial-intelligence': 'AI', 'gaming': 'gaming', 'real-world-assets-rwa': 'RWA',
    'exchange-based-tokens': 'exchange', 'decentralized-exchange': 'DEX', 'liquid-staking-tokens': 'LST',
    'oracle': 'oracle', 'privacy-coins': 'privacy', 'storage': 'storage', 'metaverse': 'metaverse',
    'solana-meme-coins': 'meme', 'depin': 'DePIN',
}
URL = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&category={}&per_page=250&page={}'
CACHE = os.path.join('models', 'sectors.json')


def base_of(symbol: str) -> str:
    """'1000PEPE/USDT:USDT' / '1000PEPEUSDT' -> 'PEPE' (unit multipliers dropped)."""
    base = symbol.split('/')[0]
    if base.endswith('USDT') and '/' not in symbol:
        base = base[:-4]
    return re.sub(r'^(1000000|1000|1M|1MB|10000|100)', '', base.upper()) or base.upper()


def _fetch(category: str, pages: int = 2) -> list:
    rows = []
    for page in range(1, pages + 1):
        req = urllib.request.Request(URL.format(category, page), headers={'accept': 'application/json'})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    batch = json.loads(resp.read().decode('utf-8'))
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 4:
                    raise
                time.sleep(30 * (attempt + 1))       # rate limited: the public API allows a few calls a minute
        rows += batch
        time.sleep(6)
        if len(batch) < 250:
            break
    return rows


def load(max_age_sec: float = 86400) -> Dict[str, str]:
    """{base symbol: sector}; empty when CoinGecko is unreachable and there is no cache."""
    try:
        if os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < max_age_sec:
            with open(CACHE, encoding='utf-8') as fh:
                return json.load(fh)
    except Exception as e:
        errors.report('sectors.cache', e, f"{CACHE} unreadable, refetching")
    best: Dict[str, tuple] = {}
    try:
        for cat, name in CATEGORIES.items():
            for r in _fetch(cat):
                sym, cap = (r.get('symbol') or '').upper(), r.get('market_cap') or 0
                if sym and (sym not in best or cap > best[sym][1]):
                    best[sym] = (name, cap)
    except Exception as e:
        errors.report('sectors.coingecko', e, 'using the cached sectors' if os.path.exists(CACHE) else 'no sectors at all')
        if os.path.exists(CACHE):
            with open(CACHE, encoding='utf-8') as fh:
                return json.load(fh)
        return {}
    out = {k: v[0] for k, v in best.items()}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, 'w', encoding='utf-8') as fh:
        json.dump(out, fh)
    return out


def sector_of(symbol: str, mapping: Dict[str, str]) -> Optional[str]:
    return mapping.get(base_of(symbol))
