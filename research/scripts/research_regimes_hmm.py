"""
Plan 3.4 (eng-59): market regimes by a Gaussian HMM vs the live GaussianMixture (ml.RegimeModel), pre-registered.

Data: the regime history of pretrained.pkl (the live model's features per closed 15m candle: BTC 1h move / volatility,
breadth, median funding / OI change / RVOL - pretrained months + live), standardized on the training part.
Split: the older 70% trains, the newer 30% tests. k = the GMM's BIC choice on the training part (2..6, as live);
the HMM uses the same k (diagonal covariances, Baum-Welch, 5 restarts, the best training likelihood).
Metrics on the test part: log-likelihood per candle (the HMM's by the forward algorithm, the GMM's per point), the
mean regime duration in candles and the switches per day of the labels (Viterbi for the HMM, argmax for the GMM).
Decision rule: the HMM replaces the GMM only if its test log-likelihood is higher AND its mean duration is at least
twice the GMM's (a regime that flips every few candles is no regime to mute a setup in).
hmmlearn has no wheel for Python 3.14: the HMM is written here (numpy, log-space forward-backward).

Run: .venv\\Scripts\\python research_regimes_hmm.py [--out research/regimes_hmm.md]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import os
import pickle

import numpy as np
from sklearn.mixture import GaussianMixture


def log_gauss(X, mu, var):
    """[n, k] log densities of diagonal Gaussians."""
    return -0.5 * (((X[:, None, :] - mu[None]) ** 2 / var[None]).sum(-1) + np.log(2 * np.pi * var).sum(-1)[None])


def lse(a, axis):
    m = a.max(axis=axis, keepdims=True)
    return (m + np.log(np.exp(a - m).sum(axis=axis, keepdims=True))).squeeze(axis)


def forward(logb, logA, logpi):
    n, k = logb.shape
    la = np.empty((n, k))
    la[0] = logpi + logb[0]
    for t in range(1, n):
        la[t] = lse(la[t - 1][:, None] + logA, 0) + logb[t]
    return la


def backward(logb, logA):
    n, k = logb.shape
    lb = np.zeros((n, k))
    for t in range(n - 2, -1, -1):
        lb[t] = lse(logA + (logb[t + 1] + lb[t + 1])[None], 1)
    return lb


def fit_hmm(X, k, rng, iters=60):
    gm = GaussianMixture(k, covariance_type='diag', random_state=int(rng.integers(1e6))).fit(X)
    mu, var = gm.means_.copy(), np.maximum(gm.covariances_.copy(), 1e-4)
    A = np.full((k, k), 0.05 / max(1, k - 1))
    np.fill_diagonal(A, 0.95)
    pi = np.full(k, 1 / k)
    prev = -np.inf
    for _ in range(iters):
        logb = log_gauss(X, mu, var)
        la, lb = forward(logb, np.log(A), np.log(pi)), backward(logb, np.log(A))
        ll = lse(la[-1], 0)
        g = np.exp(la + lb - ll)
        xi = np.zeros((k, k))
        for t in range(len(X) - 1):
            xi += np.exp(la[t][:, None] + np.log(A) + (logb[t + 1] + lb[t + 1])[None] - ll)
        A = xi / xi.sum(1, keepdims=True)
        pi = g[0] / g[0].sum()
        w = g.sum(0)
        mu = (g.T @ X) / w[:, None]
        var = np.maximum((g.T @ X ** 2) / w[:, None] - mu ** 2, 1e-4)
        if ll - prev < 1e-3 * abs(ll):
            break
        prev = ll
    return mu, var, A, pi, ll


def viterbi(logb, logA, logpi):
    n, k = logb.shape
    d = logpi + logb[0]
    back = np.zeros((n, k), int)
    for t in range(1, n):
        s = d[:, None] + logA
        back[t] = s.argmax(0)
        d = s.max(0) + logb[t]
    path = np.empty(n, int)
    path[-1] = d.argmax()
    for t in range(n - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def durations(labels):
    runs, cur = [], 1
    for a, b in zip(labels, labels[1:]):
        if a == b:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    runs.append(cur)
    return float(np.mean(runs)), (len(runs) - 1) / (len(labels) / 96)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join('research', 'regimes_hmm.md'))
    args = ap.parse_args()
    hist = pickle.load(open('pretrained.pkl', 'rb'))['regime_history']
    keys = sorted(hist)
    X = np.array([hist[t] for t in keys], float)
    X = X[~np.isnan(X).any(1)]
    cut = int(len(X) * 0.7)
    mean, sd = X[:cut].mean(0), X[:cut].std(0) + 1e-12
    Z = (X - mean) / sd
    tr, te = Z[:cut], Z[cut:]
    bics = {k: GaussianMixture(k, covariance_type='full', random_state=0).fit(tr).bic(tr) for k in range(2, 7)}
    k = min(bics, key=bics.get)
    gmm = GaussianMixture(k, covariance_type='full', random_state=0).fit(tr)
    g_ll = gmm.score(te)
    g_dur, g_sw = durations(gmm.predict(te))
    rng = np.random.default_rng(3)
    best = None
    for _ in range(5):
        m = fit_hmm(tr, k, rng)
        if best is None or m[4] > best[4]:
            best = m
    mu, var, A, pi, _ = best
    logb = log_gauss(te, mu, var)
    h_ll = float(lse(forward(logb, np.log(A), np.log(pi))[-1], 0)) / len(te)
    h_dur, h_sw = durations(viterbi(logb, np.log(A), np.log(pi)))
    adopt = h_ll > g_ll and h_dur >= 2 * g_dur
    lines = ['# Regimes: Gaussian HMM vs GaussianMixture (plan 3.4)', '',
             f"{len(X)} candles of 15m ({len(tr)} train / {len(te)} test); k = {k} by BIC "
             f"({', '.join(f'{a}: {b:.0f}' for a, b in bics.items())}).", '',
             '| model | test log-lik / candle | mean regime duration (candles) | switches per day |', '|---|---:|---:|---:|',
             f"| GMM (live, full cov.) | {g_ll:.3f} | {g_dur:.1f} | {g_sw:.1f} |",
             f"| HMM (diag. cov.) | {h_ll:.3f} | {h_dur:.1f} | {h_sw:.1f} |", '',
             'HMM stay probabilities: ' + ', '.join(f"{A[i, i]:.3f}" for i in range(k)), '',
             f"Verdict: {'replace the GMM by the HMM' if adopt else 'keep the GMM'} (rule: higher test likelihood and "
             f"at least 2x the mean duration)."]
    text = '\n'.join(lines)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
