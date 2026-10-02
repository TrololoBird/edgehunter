"""
C3 of ML_PLAN.md: GaussianMixture vs the sticky HMM (ml.StickyHMM) as the market-regime model, on the market
history saved by pretraining (pretrained.pkl `regime_history`; any older pkl with it works). Both label every candle
walk-forward (weekly refits on the past only, RegimeModel.labels_walk_forward). Reported per model: mean regime run
length (candles), switches per day, the distinct names used, how often a name's center moved after a refit, and -
when pretrain_rows exist - the 4h Edge of directional rows by regime (a context is only useful if it separates).

    python research_regimes.py [--source current|eng7]   (pretrained.pkl / models/pretrained.eng-7.pkl)
"""
import argparse
import os
import pickle
import time
from dataclasses import replace

import numpy as np

_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(_ROOT, 'research', 'regimes_c3.md')
SOURCES = {'current': os.path.join(_ROOT, 'pretrained.pkl'),
           'eng7': os.path.join(_ROOT, 'models', 'pretrained.eng-7.pkl')}


def runs(labels):
    lens, cur = [], 1
    for a, b in zip(labels[:-1], labels[1:]):
        if a == b:
            cur += 1
        else:
            lens.append(cur)
            cur = 1
    lens.append(cur)
    return np.asarray(lens)


def main():
    ap = argparse.ArgumentParser()
    # a fixed choice of our own files: a pickle is never loaded from a path given on the command line
    ap.add_argument('--source', choices=tuple(SOURCES), default='current')
    args = ap.parse_args()
    args.pkl = SOURCES[args.source]
    import config
    import ml
    with open(args.pkl, 'rb') as fh:
        hist = pickle.load(fh)['regime_history']
    lines = [f"# Regimes: GaussianMixture vs sticky HMM (C3), {len(hist)} market candles from {os.path.basename(args.pkl)}",
             '', 'Walk-forward labels (weekly refits on the past only). Longer runs / fewer switches = a steadier context.',
             '', '| Model | names used | mean run (candles) | median run | switches / day | fit time |',
             '|---|---|---:|---:|---:|---:|']
    labels_by = {}
    for kind in ('gmm', 'hmm'):
        config.CONFIG = replace(config.CONFIG, ml=replace(config.CONFIG.ml, regime_model=kind))
        ml.CONFIG = config.CONFIG
        m = ml.RegimeModel()
        m.history = dict(hist)
        t0 = time.time()
        lab = m.labels_walk_forward()
        dt = time.time() - t0
        stamps = sorted(lab)
        seq = [lab[t] for t in stamps]
        labels_by[kind] = lab
        r = runs(seq)
        days = (stamps[-1] - stamps[0]) / 86_400_000 if stamps else 1
        lines.append(f"| {kind} | {', '.join(sorted(set(seq)))} | {r.mean():.1f} | {np.median(r):.0f} | "
                     f"{(len(r) - 1) / days:.1f} | {dt:.0f}s |")
    rows_dir = config.CONFIG.pretrain.dataset_path
    if os.path.isdir(rows_dir):
        import glob
        import polars as pl
        from validation import block_stats
        df = pl.concat([pl.read_parquet(f, columns=['ts_ms', 'direction', 'ret_4h', 'baseline_mean_4h'])
                        for f in sorted(glob.glob(os.path.join(rows_dir, '*.parquet')))], how='vertical_relaxed')
        df = df.filter((pl.col('direction') != 0) & pl.col('baseline_mean_4h').is_not_null())
        q = (df['ts_ms'].to_numpy() - 5_000) // 900_000 * 900_000 - 900_000
        edge = df['direction'].to_numpy() * (df['ret_4h'].to_numpy() - df['baseline_mean_4h'].to_numpy())
        blocks = (df['ts_ms'].to_numpy() // (4 * 3_600_000)) * 2 + (df['direction'].to_numpy() > 0)
        for kind, lab in labels_by.items():
            reg = np.asarray([lab.get(int(t), '') for t in q])
            lines += ['', f"## Edge 4h of directional pretraining rows by {kind} regime", '',
                      '| Regime | rows | Edge 4h [90%] |', '|---|---:|---|']
            for name in sorted(set(reg) - {''}):
                m_ = reg == name
                mean, lo, hi, _, _ = block_stats(edge[m_], blocks[m_])
                lines.append(f"| {name} | {m_.sum()} | {mean * 100:+.3f}% [{lo * 100:+.3f}..{hi * 100:+.3f}] |")
    lines += ['', 'Decision rule (ML_PLAN.md C3): switch CONFIG.ml.regime_model to hmm only if its runs are longer and '
              'its Edge split separates at least as well.']
    text = '\n'.join(lines) + '\n'
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
