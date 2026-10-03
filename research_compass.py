"""
Checks the testable claims of the Compass review (SMC / ICT / liquidity / pumps, 2026-10) on our own data: the journal
(signals.db), the liquidations table and Binance REST candles. Writes research/compass_check.md. Read-only.

    .venv/Scripts/python research_compass.py
"""
import datetime as dt
import json
import math
import sqlite3
import statistics as st
import time
import urllib.request
from collections import defaultdict

COINS = ['BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'DOGE', 'ADA', 'LINK', 'AVAX', 'SUI', 'LTC', 'DOT', 'UNI', 'NEAR', 'APT',
         'ARB', 'OP', 'FIL', 'INJ', 'TIA', 'WLD', 'ENA', '1000PEPE', 'HBAR']
OUT = []


def say(s=''):
    print(s)
    OUT.append(s)


def klines(sym, interval, limit_total):
    out, end = [], None
    while len(out) < limit_total:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}USDT&interval={interval}&limit=1500"
        if end:
            url += f"&endTime={end}"
        rows = json.load(urllib.request.urlopen(url, timeout=30))
        if not rows:
            break
        out = rows + out
        end = int(rows[0][0]) - 1
        if len(rows) < 1500:
            break
        time.sleep(0.2)
    return [[int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7])] for r in out[-limit_total:]]


def tstat(xs):
    if len(xs) < 3:
        return 0.0
    sd = st.pstdev(xs)
    return st.fmean(xs) / (sd / math.sqrt(len(xs))) if sd else 0.0


def corr(a, b):
    ma, mb = st.fmean(a), st.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else 0.0


def main():
    db = sqlite3.connect('file:signals.db?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    say('# Compass review claims checked on our data')
    say(f'Generated {dt.datetime.now():%Y-%m-%d %H:%M}. Journal: signals.db; candles: Binance USD-M REST.')

    # 1. funding stuck at 0.01% (Binance formula: F = I while the premium is inside the neutral band)
    say('\n## 1. Binance funding sits at exactly 0.01% most of the time')
    rows = db.execute("SELECT funding_8h FROM signals WHERE funding_8h IS NOT NULL AND kind IN ('setup','anomaly')").fetchall()
    f = [r[0] for r in rows]
    exact = sum(1 for x in f if abs(x - 0.0001) < 1e-9)
    say(f'- journal rows with a funding reading: {len(f)}; exactly 0.0100%: {exact / len(f):.1%}; '
        f'> +0.03%: {sum(x >= 0.0003 for x in f) / len(f):.1%}; < -0.01%: {sum(x <= -0.0001 for x in f) / len(f):.1%}')
    say('- Claim: CONFIRMED if most readings are exactly 0.01% (the funding is uninformative inside the band).')

    # 2. forceOrder: at most one order per symbol per second
    say('\n## 2. Binance forceOrder stream: <= 1 order per symbol per second (a lower bound of liquidations)')
    try:
        cols = [r[1] for r in db.execute("PRAGMA table_info(liquidations)")]
        tcol = 'ts_ms' if 'ts_ms' in cols else cols[0]
        q = (f"SELECT symbol, {tcol} / 1000 AS s, COUNT(*) n FROM liquidations WHERE venue = 'binance' "
             f"GROUP BY symbol, s ORDER BY n DESC LIMIT 1")
        top = db.execute(q).fetchone()
        tot = db.execute("SELECT venue, COUNT(*), SUM(usd) FROM liquidations GROUP BY venue").fetchall()
        say(f'- max Binance events for one symbol in one second: {top[2] if top else "n/a"}')
        for v, n, usd in tot:
            say(f'- {v}: {n} events, ${(usd or 0) / 1e6:.1f}M')
        say('- Claim: CONFIRMED if the max is 1 and Binance shows far fewer events than Bybit (complete feed).')
    except Exception as e:
        say(f'- not checked: {e}')

    # 3. seasonality: volume / volatility strong, returns weak; weekend volume ~30% lower
    say('\n## 3. Intraday seasonality: volume and volatility yes, returns no; weekend volume ~30% lower')
    by_hour_vol, by_hour_rng, by_hour_ret = defaultdict(list), defaultdict(list), defaultdict(list)
    wk_vol, we_vol = [], []
    for c in COINS:
        k = klines(c, '1h', 2160)
        mean_v = st.fmean(x[5] for x in k)
        for p, x in zip(k, k[1:]):
            d = dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc)
            by_hour_vol[d.hour].append(x[5] / mean_v)
            by_hour_rng[d.hour].append((x[2] - x[3]) / x[1])
            by_hour_ret[d.hour].append(x[4] / p[4] - 1)
            (we_vol if d.weekday() >= 5 else wk_vol).append(x[5] / mean_v)
    vols = {h: st.fmean(v) for h, v in by_hour_vol.items()}
    rngs = {h: st.fmean(v) for h, v in by_hour_rng.items()}
    ts = {h: tstat(v) for h, v in by_hour_ret.items()}
    say(f'- {len(COINS)} coins x 90 days of 1h candles')
    say(f'- volume, max / min hour: {max(vols.values()) / min(vols.values()):.2f}x '
        f'(peak {max(vols, key=vols.get):02d} UTC, low {min(vols, key=vols.get):02d} UTC)')
    say(f'- range, max / min hour: {max(rngs.values()) / min(rngs.values()):.2f}x')
    sig = sorted((h for h, t in ts.items() if abs(t) > 2), key=lambda h: h)
    say(f'- hourly mean returns with |t| > 2: {len(sig)} of 24 ({", ".join(f"{h:02d}h t={ts[h]:+.1f}" for h in sig) or "none"}); '
        f'~1.2 expected by chance (pooled coins are correlated, so t is overstated)')
    say(f'- 21-23 UTC mean return: {st.fmean(by_hour_ret[21] + by_hour_ret[22] + by_hour_ret[23]) * 100:+.3f}% per hour '
        f'vs all hours {st.fmean([x for v in by_hour_ret.values() for x in v]) * 100:+.3f}%')
    say(f'- weekend volume vs weekdays: {st.fmean(we_vol) / st.fmean(wk_vol) - 1:+.0%}')

    # 4. correlations rise in stress; downside beta
    say('\n## 4. Alt correlation with BTC rises on down days')
    btc = klines('BTC', '1d', 365)
    rb = {x[0]: x[4] / p[4] - 1 for p, x in zip(btc, btc[1:])}
    down_c, up_c, beta_dn, beta_up = [], [], [], []
    for c in COINS[1:]:
        k = klines(c, '1d', 365)
        ra = {x[0]: x[4] / p[4] - 1 for p, x in zip(k, k[1:])}
        days = sorted(set(ra) & set(rb))
        dn = [d for d in days if rb[d] < 0]
        up = [d for d in days if rb[d] >= 0]
        if len(dn) > 30 and len(up) > 30:
            down_c.append(corr([ra[d] for d in dn], [rb[d] for d in dn]))
            up_c.append(corr([ra[d] for d in up], [rb[d] for d in up]))
            for sel, out in ((dn, beta_dn), (up, beta_up)):
                xb = [rb[d] for d in sel]
                ya = [ra[d] for d in sel]
                vb = st.pvariance(xb)
                out.append(sum((x - st.fmean(xb)) * (y - st.fmean(ya)) for x, y in zip(xb, ya)) / len(xb) / vb)
    say(f'- median correlation with BTC: BTC-down days {st.median(down_c):.2f}, BTC-up days {st.median(up_c):.2f}')
    say(f'- median beta: down days {st.median(beta_dn):.2f}, up days {st.median(beta_up):.2f}')

    # 5. order flow: contemporaneous vs predictive
    say('\n## 5. Taker flow explains the SAME interval\'s move, predicts the next one much less')
    rows = db.execute("SELECT delta_ratio, price_change_5m, ret_15m, ret_1h FROM signals WHERE kind = 'anomaly' AND "
                      "delta_ratio IS NOT NULL AND price_change_5m IS NOT NULL AND ret_15m IS NOT NULL").fetchall()
    if len(rows) > 100:
        dr = [r[0] for r in rows]
        say(f'- {len(rows)} anomaly rows: corr(5m taker delta, same 5m move) {corr(dr, [r[1] for r in rows]):+.2f}; '
            f'corr(5m delta, next 15m) {corr(dr, [r[2] for r in rows]):+.2f}; '
            f'next 1h {corr(dr, [r[3] for r in rows if r[3] is not None][:len(dr)]) if all(r[3] is not None for r in rows) else float("nan"):+.2f}')

    # 6. price x OI quadrants (classic reading) vs the next 4h
    say('\n## 6. Price x OI quadrants vs the next 4h (anomaly rows, raw returns)')
    rows = db.execute("SELECT price_change_5m p, oi_change_5m o, ret_4h r FROM signals WHERE kind='anomaly' AND "
                      "ret_4h IS NOT NULL AND oi_change_5m IS NOT NULL AND price_change_5m IS NOT NULL").fetchall()
    quad = defaultdict(list)
    for p, o, r in rows:
        if abs(p) < 0.003 or o == 0:
            continue
        quad[('price up' if p > 0 else 'price down', 'OI up' if o > 0 else 'OI down')].append(r)
    for k, v in sorted(quad.items()):
        say(f'- {k[0]} / {k[1]}: n {len(v)}, next 4h {st.fmean(v) * 100:+.2f}% (t {tstat(v):+.1f}), up {sum(x > 0 for x in v) / len(v):.0%}')

    # 7. sweep / reversal setups: reversal or continuation (Mahadzva)
    say('\n## 7. Swept level -> continuation, not reversal (Mahadzva, FX)')
    for key in ('SWEEP LOW', 'SWEEP HIGH', 'SILVER BULLET LONG', 'SILVER BULLET SHORT', 'SPRING', 'UTAD',
                'FLUSH REVERSAL', 'SQUEEZE REVERSAL'):
        v = [r[0] * r[1] for r in db.execute("SELECT direction, ret_4h FROM signals WHERE kind='setup' AND group_key=? "
                                               "AND ret_4h IS NOT NULL", (key,))]
        if v:
            say(f'- {key}: n {len(v)}, 4h in the reversal direction {st.fmean(v) * 100:+.2f}% (t {tstat(v):+.1f}), '
                f'right side {sum(x > 0 for x in v) / len(v):.0%}')
    say('- Archive (research/cards_6m.md, 202k cards): sweep low -0.27R, sweep high -0.06R as reversal trades.')

    # 8. claims answered by earlier archive studies
    say('\n## 8. Claims already tested by our archive studies (research-findings)')
    say('- "Levels / EQH-EQL / S-R zones attract and reject price": hit rates at the random-walk rate (eqh.md, '
        'level_triggers.md, scenario_model.md) -> consistent with the review\'s "folklore / medium as a map".')
    say('- "TSMOM 1-4 weeks works in crypto": daily TSMOM / XSMOM did NOT replicate 2023-10..2026-09 (trend_daily.md) '
        '-> the review\'s [Empirical+] is not confirmed on recent Binance perps.')
    say('- "Funding / positioning predicts returns": only the funding level passed in-sample, its holdout failed '
        '(funding_holdout.md) -> weaker than the review states.')
    say('- "Pumps retrace": small-cap pumps come back to 50% of the move before a new high in 73-82% (pumps.md) -> '
        'consistent; the 30-minute round trip is about organised spot P&Ds, not measured here.')
    say('- "Meta-labeling is the way to use SMC": our meta-model AUC 0.63 still selected losing trades (-0.10R, meta_12m.md).')

    with open('research/compass_check.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(OUT) + '\n')


if __name__ == '__main__':
    main()
