# ruff: noqa: E741  (O / H / L / C are the candle fields)
"""
Train the scenario card's probability: P(the first resistance above is touched before the first support below),
on the Binance archive's 1h candles with the SAME level / feature code the bot runs (`scenarios.py`).

Samples: every coin of the point-in-time universe (research_htf.market_state: spot pair, >= $10M average volume over
the 30 days before, >= 100 days listed; delisted coins included), every 12h, the last 200 1h candles as the bot's
`MarketData.h1`. Label: which of the two levels the next 72 1h candles touch first (samples touching neither, or both
inside one candle, are dropped). Split in TIME: train the oldest 60%, calibrate (isotonic) the next 15%, test the
newest 25%, 72h embargo between them. Baseline: the geometric p_geo = d_down / (d_up + d_down) (a driftless random
walk). The model is saved with passed=True only if it beats the baseline on the test part in Brier score AND log
loss; the bot uses it only then. The report also prices a trade on the call (long toward the resistance with the
stop at the support when p >= 0.6, short when p <= 0.4), net of 0.20% round trip.

Run: python train_scenarios.py [--months 38] [--limit N] [--step 12]
"""
import argparse
import multiprocessing as mp
import os
import pickle
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

import research_htf as rh
from macro import MACRO_FEATURES, Macro
from scenarios import FEATURES, MODEL_PATH, brier, build, label_first_touch, logloss

G: Dict = {}
HORIZON = 72
WINDOW = 200


def coin_samples(j: int) -> List[Dict]:
    O, H, L, C, V = (G[k][:, j] for k in ('O', 'H', 'L', 'C', 'V'))
    btc = G['C'][:, 0]
    t0, step = G['t0'], G['step']
    elig = G['elig'][:, j]
    out: List[Dict] = []
    n = len(C)
    for t in range(WINDOW, n - HORIZON, step):
        day = t // 24 - 1
        if day < 0 or not elig[day]:
            continue
        sl = slice(t - WINDOW, t)
        if np.isnan(C[sl]).any():
            continue
        ts = [t0 + (t - WINDOW + i) * rh.HOUR for i in range(WINDOW)]
        candles = [[ts[i], O[t - WINDOW + i], H[t - WINDOW + i], L[t - WINDOW + i], C[t - WINDOW + i],
                    V[t - WINDOW + i]] for i in range(WINDOW)]
        b = btc[sl]
        sc = build(candles, float(C[t - 1]), t0 + t * rh.HOUR, None if np.isnan(b).any() else b.tolist(),
                   model=False)
        if sc is None:
            continue
        up, down = sc['above'][0]['lo'], sc['below'][0]['hi']
        y = label_first_touch(H[t:t + HORIZON], L[t:t + HORIZON], up, down)
        if y is None:
            continue
        row = dict(sc['features'])
        row.update(ts=t0 + t * rh.HOUR, coin=G['coins'][j], y=y, price=float(C[t - 1]), up=up, down=down)
        out.append(row)
    return out


def _worker(j):
    try:
        return coin_samples(j)
    except Exception as e:
        return [{'error': f"{G['coins'][j]}: {type(e).__name__} {e}"}]


def fmt(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d')


def trade_r(df, p, lo=0.4, hi=0.6):
    """Net R of trading the call from the price: long to `up`, stop at `down` (p >= hi); short mirror."""
    price, up, down, y = (df[k].to_numpy() for k in ('price', 'up', 'down', 'y'))
    cost = rh.COST * price
    rs, picks = [], []
    for i in range(len(p)):
        if p[i] >= hi:
            risk, reward, win = price[i] - down[i], up[i] - price[i], y[i] == 1
        elif p[i] <= lo:
            risk, reward, win = up[i] - price[i], price[i] - down[i], y[i] == 0
        else:
            continue
        if risk <= 0:
            continue
        rs.append(((reward if win else -risk) - cost[i]) / risk)
        picks.append(i)
    return np.asarray(rs), picks


def main():
    import lightgbm as lgb
    import polars as pl
    from sklearn.isotonic import IsotonicRegression
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=38)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--step', type=int, default=12)
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--out', default=os.path.join('research', 'scenario_model.md'))
    parser.add_argument('--samples', default='')
    parser.add_argument('--from-samples', default='', help='skip the archive pass: train on a saved samples file')
    args = parser.parse_args()
    errors: List[str] = []
    if args.from_samples:
        df = pl.read_parquet(args.from_samples).sort('ts')
        n_coins = df['coin'].n_unique()
    else:
        t0, coins, O, H, L, C, V, _ = rh.load(args.months, args.limit)
        elig, _, _, _ = rh.market_state(C, V, coins)
        G.update(t0=t0, coins=coins, O=O, H=H, L=L, C=C, V=V, elig=elig, step=args.step)
        print(f"{len(coins)} coins, {C.shape[0]} hours", flush=True)
        rows: List[Dict] = []
        with mp.get_context('fork').Pool(args.workers) as pool:
            for k, res in enumerate(pool.imap_unordered(_worker, range(len(coins)), chunksize=2)):
                rows.extend(res)
                if k % 50 == 0:
                    print(f"  {k}/{len(coins)} coins, {len(rows)} samples", flush=True)
        errors = [r['error'] for r in rows if 'error' in r]
        df = pl.DataFrame([r for r in rows if 'error' not in r]).sort('ts')
        n_coins = len(coins)
        if args.samples:
            df.write_parquet(args.samples)
    # macro context (FRED, known from the day after its date): a candidate input, kept only if it helps on the
    # calibration part (the test part is looked at once, after the choice)
    mac = Macro()
    have_macro = mac.refresh()
    if have_macro:
        cache: Dict[int, Dict[str, float]] = {}
        cols = {k: [] for k in MACRO_FEATURES}
        for t in df['ts'].to_list():
            day = int(t) // 86_400_000
            if day not in cache:
                cache[day] = mac.features(float(t))
            for k in MACRO_FEATURES:
                cols[k].append(cache[day][k])
        df = df.with_columns([pl.Series(k, v, dtype=pl.Float64) for k, v in cols.items()])
    n = len(df)
    ts = df['ts'].to_numpy()
    t_a, t_b = ts[int(n * 0.60)], ts[int(n * 0.75)]
    emb = HORIZON * rh.HOUR
    train = df.filter(pl.col('ts') < t_a - emb)
    calib = df.filter((pl.col('ts') >= t_a) & (pl.col('ts') < t_b - emb))
    test = df.filter(pl.col('ts') >= t_b)

    def fit(cols):
        clf = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=200,
                                 subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1)
        clf.fit(train.select(cols).to_numpy(), train['y'].to_numpy())
        raw_calib = clf.predict_proba(calib.select(cols).to_numpy())[:, 1]
        return clf, raw_calib, brier(raw_calib, calib['y'].to_list())

    variants = {'price': list(FEATURES)}
    if have_macro:
        variants['price + macro'] = list(FEATURES) + list(MACRO_FEATURES)
    fitted = {name: fit(cols) for name, cols in variants.items()}
    chosen = min(fitted, key=lambda k: fitted[k][2])
    feats = variants[chosen]
    clf, raw_calib, _ = fitted[chosen]
    iso = IsotonicRegression(out_of_bounds='clip', y_min=0.01, y_max=0.99)
    iso.fit(raw_calib, calib['y'].to_numpy())
    y = test['y'].to_list()
    p_model = iso.predict(clf.predict_proba(test.select(feats).to_numpy())[:, 1])
    p_geo = test['p_geo'].to_numpy()
    base = float(np.mean(train['y'].to_numpy()))
    b_m, b_g, b_c = brier(p_model, y), brier(p_geo, y), brier([base] * len(y), y)
    l_m, l_g = logloss(p_model, y), logloss(p_geo, y)
    passed = b_m < b_g and l_m < l_g
    verdict = 'PASSED: the bot shows the model' if passed else 'NOT passed: the bot shows the geometric baseline'
    lines = [f"# Scenario probability model ({n_coins} coins, {n} samples, {fmt(ts[0])} .. {fmt(ts[-1])})", '',
             "Label: the first resistance above touched before the first support below within 72h (the scenario "
             "card's two nearest ladder levels). Code and protocol: `train_scenarios.py`, `scenarios.py`.", '',
             f"Train < {fmt(t_a)}, calibration {fmt(t_a)} .. {fmt(t_b)}, TEST from {fmt(t_b)} ({len(test)} samples, "
             f"up first {np.mean(y):.1%}).", '',
             'Feature sets, Brier of the raw model on the CALIBRATION part (the choice): ' +
             ', '.join(f"{k} {v[2]:.4f}" for k, v in fitted.items()) + f" -> **{chosen}**" +
             ('' if have_macro else ' (FRED unavailable: no macro variant)'), '',
             '| predictor (test part) | Brier | log loss |', '|---|---:|---:|',
             f"| constant base rate {base:.3f} | {b_c:.4f} | — |",
             f"| geometric p_geo = d_down / (d_up + d_down) | {b_g:.4f} | {l_g:.4f} |",
             f"| model (LightGBM + isotonic, {chosen}) | {b_m:.4f} | {l_m:.4f} |", '',
             f"Brier skill vs geometry: {(1 - b_m / b_g) * 100:+.2f}%. **{verdict}**.", '']
    lines += ['## Calibration of the model on the test part', '', '| predicted | samples | observed up-first |',
              '|---|---:|---:|']
    for lo_b in np.arange(0, 1, 0.1):
        m = (p_model >= lo_b) & (p_model < lo_b + 0.1)
        if m.sum() >= 50:
            lines.append(f"| {lo_b:.1f}-{lo_b + 0.1:.1f} | {int(m.sum())} | {np.mean(np.asarray(y)[m]):.1%} |")
    lines += ['', '## Trading the call on the test part (entry at the price, target = the level, stop = the other '
              'level, 0.20% round trip)', '', '| rule | trades | win | mean net R [90% by week] |',
              '|---|---:|---:|---|']
    wk = (test['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
    for name, p in (('model p >= 0.6 long / <= 0.4 short', p_model), ('geometry p >= 0.6 / <= 0.4', p_geo)):
        r, picks = trade_r(test, p)
        if len(r) >= 10:
            m, lo, hi, _ = rh.week_boot(r, wk[picks])
            lines.append(f"| {name} | {len(r)} | {np.mean(r > 0):.0%} | {m:+.3f} [{lo:+.3f}..{hi:+.3f}] |")
        else:
            lines.append(f"| {name} | {len(r)} | — | — |")
    imp = sorted(zip(feats, clf.feature_importances_), key=lambda x: -x[1])
    lines += ['', 'Feature importance (splits): ' + ', '.join(f"{k} {v}" for k, v in imp), '']
    if errors:
        lines += [f"{len(errors)} coins failed, first: {errors[0]}", '']
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)
    # the model fitted on the train part and calibrated on the calibration part: exactly the one tested above
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, 'wb') as fh:
        pickle.dump({'clf': clf, 'calibrator': iso, 'features': feats, 'passed': passed,
                     'trained_on': f"{fmt(ts[0])}..{fmt(t_a)}", 'brier': b_m, 'brier_geo': b_g,
                     'test_from': fmt(t_b)}, fh)

if __name__ == '__main__':
    main()
