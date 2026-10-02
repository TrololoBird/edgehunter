"""Formulas of validation.py against known values (ML_PLAN.md A1)."""
import math

import numpy as np

import validation as v


def test_norm_ppf_known_values():
    for p, z in ((0.5, 0.0), (0.975, 1.959964), (0.01, -2.326348), (0.999, 3.090232)):
        assert abs(v._norm_ppf(p) - z) < 1e-5


def test_expected_max_sharpe_matches_bailey():
    # Bailey & Lopez de Prado (2014): 10 trials of unit-variance Sharpe ratios -> E[max] ~ 1.575
    assert abs(v.expected_max_sharpe(10, 1.0) - 1.575) < 0.01
    assert v.expected_max_sharpe(1, 1.0) == 0.0
    assert v.expected_max_sharpe(1000, 1.0) > v.expected_max_sharpe(100, 1.0)


def test_psr_and_deflation():
    rng = np.random.default_rng(1)
    good = rng.normal(0.1, 1.0, 2000)                 # per-period SR ~0.1 over 2000 periods: clearly > 0
    assert v.probabilistic_sharpe(good) > 0.99
    noise = rng.normal(0.0, 1.0, 2000)
    assert 0.02 < v.probabilistic_sharpe(noise) < 0.98
    # many trials raise the bar: the same series is less convincing after 1000 attempts
    assert v.deflated_sharpe(good, 1000) < v.deflated_sharpe(good, 1)


def test_bh_known():
    q = v.bh([0.01, 0.04, 0.03, float('nan'), 0.5])
    assert math.isnan(q[3])
    # m = 4: 0.01 -> 0.04; 0.03 -> min(0.06, 0.0533); 0.04 -> 0.04 x 4 / 3
    assert abs(q[0] - 0.04) < 1e-12 and abs(q[2] - 0.04 * 4 / 3) < 1e-12 and abs(q[1] - 0.04 * 4 / 3) < 1e-12
    assert q[4] == 0.5


def test_cpcv_purges_overlapping_labels():
    t0 = np.arange(600, dtype=float)
    t1 = t0 + 10                                      # every label looks 10 steps ahead
    splits = list(v.cpcv_splits(t0, t1, n_groups=6, k_test=2, embargo=0.01))
    assert len(splits) == math.comb(6, 2)
    assert v.cpcv_paths(6, 2) == 5
    for train, test, _ in splits:
        assert not set(train) & set(test)
        # no training label window touches a test label window
        tr0, tr1 = t0[train], t1[train]
        for g in np.split(np.sort(test), np.flatnonzero(np.diff(np.sort(test)) > 1) + 1):
            lo, hi = t0[g].min(), t1[g].max()
            assert not np.any((tr0 <= hi) & (tr1 >= lo))


def test_pbo_noise_vs_skill():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, (160, 20))
    p_noise, _ = v.pbo(noise)
    assert 0.25 < p_noise < 0.75                      # unskilled variants: the IS winner is a coin flip OOS
    skill = noise.copy()
    skill[:, 0] += 1.0                                # one variant truly better in every period
    p_skill, _ = v.pbo(skill)
    assert p_skill < 0.05
