"""
eng-134 research tool, NOT part of the bot: CoinGlass's order-book liquidity heatmap (the site's internal endpoint
capi.coinglass.com, keyless; verified 2026-10-16). 100 points of resting book liquidity by price: interval 1d =
100 days, 1h = ~4 days. CoinGlass's official API needs a key; this endpoint is undocumented and may change or close
any day, and scraping may be against their terms - research snapshots only, never a live input. ~2.7 MB per BTC call.

    python tools/coinglass_heatmap.py ANIME BTC --interval 1h --out research/coinglass

Writes <out>/<SYMBOL>_<interval>_<YYYYmmddHHMM>.json: {"symbol", "interval", "size" (price step), "max",
"data": [[unix_s, [[price, liquidity], ...]], ...]} exactly as served.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

URL = 'https://capi.coinglass.com/liquidity-heatmap/api/liquidity/v4/heatmap?symbol=Binance_{}USDT&interval={}'


def fetch(coin: str, interval: str) -> dict:
    req = urllib.request.Request(URL.format(coin.upper(), interval), headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        d = json.load(resp)
    data = d.get('data')
    if not isinstance(data, dict) or not data.get('data'):
        raise ValueError(f"empty answer: {str(d)[:120]}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('coins', nargs='+')
    ap.add_argument('--interval', default='1h', help="1h / 4h / 1d (whatever the site serves)")
    ap.add_argument('--out', default=os.path.join('research', 'coinglass'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    stamp, failed = time.strftime('%Y%m%d%H%M', time.gmtime()), 0
    for coin in a.coins:
        try:
            data = fetch(coin, a.interval)
        except Exception as e:
            print(f"{coin}: {e!r}", file=sys.stderr)
            failed += 1
            continue
        path = os.path.join(a.out, f"{coin.upper()}_{a.interval}_{stamp}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'symbol': coin.upper(), 'interval': a.interval, **data}, f)
        print(f"{coin}: {len(data['data'])} points, step {data.get('size')} -> {path}")
        time.sleep(2)                              # politeness: one call at a time
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
