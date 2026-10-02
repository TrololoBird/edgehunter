"""
Machine learning that adapts to the current market instead of fixed thresholds fitted to the past.

1. AnomalyModel (scikit-learn IsolationForest): Tier-0 anomalies as an UNUSUAL COMBINATION of a coin's live
   features (RVOL, price / OI z-scores, whale sweeps, liquidations, flow intensity, one-venue share, algo
   clusters), refitted every hour on the last hours of the whole universe. It replaces the OR of seven fixed
   thresholds (which flagged ~1000 onsets an hour, most of them noise) once it has been fitted; until then the
   rules decide. No labels needed.
2. RegimeModel (scikit-learn GaussianMixture): the market regime from market-wide features of every closed 15m
   candle (BTC 1h move and volatility, breadth, median funding / OI change / RVOL). Clusters are named from their
   centers ('up·volatile', 'flat·quiet', ...). Every journal row carries the regime; stats.py splits Edge by it
   and journal.veto_reason mutes a setup whose Edge in the current regime is proven negative.
3. SuccessModel (river, online logistic regression + ADWIN drift detection): P(4h Edge > 0) of a directional
   signal from the features stored in the journal. It learns from every labelled row as it comes in (and replays
   the journal after a restart), and starts over when ADWIN detects that its errors drifted (regime change).
   Shadow mode: stored in the journal and shown on cards once trained, never used as a filter until stats.py
   proves it separates winners from losers.
"""
import logging
import json
import math
import threading
import time
from collections import deque
from typing import Dict, List, Optional

import numpy as np
import polars as pl

from config import CONFIG

logger = logging.getLogger(__name__)


def _log1p_abs(x) -> float:
    return math.log1p(abs(float(x or 0.0)))


# ====================================================================== 1. anomalies

# IsolationForest runs in its own process. In a worker THREAD scikit-learn held the GIL through its per-tree loops
# (40-90ms per scoring every 2s, seconds per hourly fit), and the event loop waited for the GIL even to read its
# sockets (the watchdog caught it: loop in ssl.read, worker thread in score, 1-2s stalls at every market burst).
_WORKER_MODEL = None


def _worker_fit(X: np.ndarray, quantile: float):
    """(worker process) Fit, keep the model for scoring, return it pickled with its threshold."""
    import pickle
    from sklearn.ensemble import IsolationForest
    global _WORKER_MODEL
    model = IsolationForest(n_estimators=100, max_samples=256, random_state=0, n_jobs=1).fit(X)
    threshold = float(np.quantile(model.score_samples(X), quantile))
    _WORKER_MODEL = model
    return pickle.dumps(model), threshold


def _worker_load(blob: Optional[bytes]) -> bool:
    """(worker process) Install a model restored from ml_state.pkl."""
    import pickle
    global _WORKER_MODEL
    _WORKER_MODEL = pickle.loads(blob) if blob else None
    return _WORKER_MODEL is not None


def _worker_score(X: np.ndarray) -> Optional[np.ndarray]:
    """(worker process) score_samples of the current vectors (lower = more unusual)."""
    return _WORKER_MODEL.score_samples(X) if _WORKER_MODEL is not None else None


class AnomalyModel:
    FEATURES = ('rvol', 'price_z', 'oi_z', 'whales', 'liquidations', 'cluster', 'one_venue', 'perp_flow', 'spot_flow')

    def __init__(self):
        cfg = CONFIG.ml
        rows = int(cfg.anomaly_window_sec / cfg.anomaly_sample_every_sec * CONFIG.exchange.max_pairs * 1.2)
        # The training window: feature vectors and their sample times (kept across restarts in ml_state.pkl, so a
        # restart neither loses the window nor leaves the model unfitted for its first ~10 minutes)
        self.samples: deque = deque(maxlen=rows)     # (sample time, feature vector)
        self.model = None
        self.threshold: Optional[float] = None
        self.fitted_at = 0.0
        self.fitting = False
        self._last_sample = 0.0
        self._pool = None              # ProcessPoolExecutor with one worker, created on first use
        self._worker_ready = False     # the worker holds the current model

    # ---------------------------------------------------------------- worker process

    def _executor(self):
        if self._pool is not None and getattr(self._pool, '_broken', False):
            # the worker died (killed when RAM ran out): a broken pool fails every call forever - Tier-0's check
            # raised BrokenProcessPool every 2s until a restart (live 2026-09-30 23:28), so a new one is started
            logger.warning("ML anomalies: the worker process died; starting a new one")
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool, self._worker_ready = None, False
        if self._pool is None:
            import multiprocessing
            import os
            from concurrent.futures import ProcessPoolExecutor
            from watchdog import exit_with_parent
            self._pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'),
                                             initializer=exit_with_parent, initargs=(os.getpid(),))
        return self._pool

    async def ascore(self, X: np.ndarray) -> Optional[np.ndarray]:
        """Scores computed in the worker process; None before the first fit."""
        import asyncio
        import pickle
        if self.model is None or not len(X):
            return None
        from concurrent.futures.process import BrokenProcessPool
        loop = asyncio.get_running_loop()
        try:
            if not self._worker_ready:
                self._worker_ready = await loop.run_in_executor(self._executor(), _worker_load,
                                                                pickle.dumps(self.model))
            return await loop.run_in_executor(self._executor(), _worker_score, X)
        except BrokenProcessPool:
            # no scores this pass (the rules still flag); the next call starts a new worker and reloads the model
            self._worker_ready = False
            return None

    async def afit(self) -> None:
        """Fit in the worker process on the sampled window; the old model keeps scoring until the new one is in."""
        import asyncio
        import pickle
        self.fitting = True
        try:
            X = self.window(time.time())
            blob, threshold = await asyncio.get_running_loop().run_in_executor(
                self._executor(), _worker_fit, X, CONFIG.ml.anomaly_quantile)
            self.model, self.threshold, self.fitted_at = pickle.loads(blob), threshold, time.time()
            self._worker_ready = True
            logger.info(f"ML anomalies: IsolationForest fitted on {len(X)} samples (worker process), "
                        f"threshold at the {CONFIG.ml.anomaly_quantile:.2%} most unusual")
        except Exception as e:
            logger.warning(f"ML anomalies: fit failed ({type(e).__name__} {e}); the previous model stays")
        finally:
            self.fitting = False

    def close(self):
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None

    @staticmethod
    def vector(m: Dict[str, float]) -> List[float]:
        """Scale-free features of one coin: z-scores, multiples of the coin's own average minute, shares."""
        avg_minute = m.get('avg_minute_usd') or 0.0
        per_minute = (lambda v: _log1p_abs((v or 0.0) / avg_minute)) if avg_minute > 0 else (lambda v: 0.0)
        venues = m.get('venues_active') or 0
        return [
            math.log1p(max(0.0, m.get('rvol_1m') or 0.0)),
            min(abs(m.get('price_z') or 0.0), 50.0),
            min(abs(m.get('oi_z') or 0.0), 50.0),
            _log1p_abs(m.get('whale_net_5m')),
            per_minute((m.get('liq_long_5m') or 0.0) + (m.get('liq_short_5m') or 0.0)),
            abs(m.get('cluster') or 0.0),
            (m.get('top_venue_share') or 0.0) if venues >= 2 else 0.0,
            per_minute(m.get('agg_cvd_5m') or m.get('futures_cvd_5m')),
            per_minute(m.get('spot_cvd_5m')),
        ]

    @property
    def ready(self) -> bool:
        return self.model is not None and self.threshold is not None

    def observe(self, X: np.ndarray, now: float, warmed_up: bool = True):
        """Sample the universe's feature vectors into the training window (every anomaly_sample_every_sec)."""
        if warmed_up and now - self._last_sample >= CONFIG.ml.anomaly_sample_every_sec and len(X):
            self._last_sample = now
            self.samples.extend((now, row) for row in X.tolist())

    def window(self, now: float) -> np.ndarray:
        """The training samples of the last anomaly_window_sec."""
        cutoff = now - CONFIG.ml.anomaly_window_sec
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()
        return np.asarray([row for _, row in self.samples], dtype=np.float64)

    def due(self, now: float) -> bool:
        cfg = CONFIG.ml
        return (not self.fitting and len(self.samples) >= cfg.anomaly_min_samples
                and (self.model is None or now - self.fitted_at >= cfg.anomaly_fit_every_sec))

    def fit(self) -> None:
        """Blocking in-process fit (offline use / tests); the live scanner uses afit (worker process)."""
        from sklearn.ensemble import IsolationForest
        self.fitting = True
        try:
            X = self.window(time.time())
            model = IsolationForest(n_estimators=100, max_samples=256, random_state=0, n_jobs=1).fit(X)
            scores = model.score_samples(X)
            threshold = float(np.quantile(scores, CONFIG.ml.anomaly_quantile))
            self.model, self.threshold, self.fitted_at = model, threshold, time.time()
            logger.info(f"ML anomalies: IsolationForest fitted on {len(X)} samples, "
                        f"threshold at the {CONFIG.ml.anomaly_quantile:.2%} most unusual")
        finally:
            self.fitting = False

    def score(self, X: np.ndarray) -> Optional[np.ndarray]:
        """score_samples of the current vectors (lower = more unusual), None before the first fit."""
        model = self.model
        if model is None or not len(X):
            return None
        return model.score_samples(X)

    def state(self) -> Dict:
        # list(deque) is one C-level copy (the loop may append meanwhile: this runs in the state-saving thread)
        samples = list(self.samples)
        return {'model': self.model, 'threshold': self.threshold, 'fitted_at': self.fitted_at,
                'times': np.asarray([t for t, _ in samples], dtype=np.float64),
                'buffer': np.asarray([row for _, row in samples], dtype=np.float32).reshape(len(samples), len(self.FEATURES))}

    def load_state(self, state: Dict):
        """
        The last model (any age: it scores until the refit replaces it, rules alone were the gap) and the training
        samples still inside the window; a model older than anomaly_fit_every_sec is refitted as soon as the window
        holds anomaly_min_samples (due()), i.e. right after the start when the downtime was short.
        """
        if not state:
            return
        if state.get('model') is not None and state.get('threshold') is not None:
            self.model, self.threshold, self.fitted_at = state['model'], state['threshold'], state.get('fitted_at', 0.0)
            self._worker_ready = False
        buffer, times = state.get('buffer'), state.get('times')
        if buffer is not None and times is not None and len(buffer) == len(times) and len(buffer)                 and np.asarray(buffer).shape[1] == len(self.FEATURES):
            keep = np.asarray(times) >= time.time() - CONFIG.ml.anomaly_window_sec
            self.samples.extend(zip(np.asarray(times)[keep].tolist(), np.asarray(buffer, dtype=np.float64)[keep].tolist()))


# ====================================================================== 2. regimes

class StickyHMM:
    """
    Gaussian hidden Markov model with diagonal covariances and a sticky transition prior (ML_PLAN.md C1): a regime
    persists, so the self-transition gets `kappa` pseudo-counts per state on every M-step (Fox et al.'s sticky HMM,
    MAP version). Labels come from the FORWARD (filtered) probabilities only - P(state_t | x_1..x_t) - never from
    smoothing or Viterbi, which would use the future. Initialised from a GaussianMixture.
    """

    def __init__(self, k: int, kappa: float, iters: int = 30, seed: int = 0):
        self.k, self.kappa, self.iters, self.seed = k, kappa, iters, seed
        self.means_ = self.vars_ = self.trans_ = self.start_ = None

    def _loglik(self, Z: np.ndarray) -> np.ndarray:
        v = self.vars_[None, :, :]
        return -0.5 * (np.log(2 * np.pi * v) + (Z[:, None, :] - self.means_[None, :, :]) ** 2 / v).sum(axis=2)

    def _forward(self, ll: np.ndarray):
        n = len(ll)
        alpha = np.empty((n, self.k))
        scale = np.empty(n)
        e = np.exp(ll - ll.max(axis=1, keepdims=True))
        a = self.start_ * e[0]
        scale[0] = a.sum()
        alpha[0] = a / scale[0]
        for t in range(1, n):
            a = (alpha[t - 1] @ self.trans_) * e[t]
            scale[t] = a.sum() or 1e-300
            alpha[t] = a / scale[t]
        return alpha, scale, e

    def fit(self, Z: np.ndarray) -> 'StickyHMM':
        from sklearn.mixture import GaussianMixture
        gm = GaussianMixture(n_components=self.k, covariance_type='diag', random_state=self.seed,
                             reg_covar=1e-3).fit(Z)
        self.means_, self.vars_ = gm.means_.copy(), gm.covariances_.copy() + 1e-3
        self.start_ = np.full(self.k, 1.0 / self.k)
        self.trans_ = np.full((self.k, self.k), 0.05 / max(1, self.k - 1))
        np.fill_diagonal(self.trans_, 0.95)
        n = len(Z)
        for _ in range(self.iters):
            ll = self._loglik(Z)
            alpha, scale, e = self._forward(ll)
            beta = np.empty((n, self.k))
            beta[-1] = 1.0
            for t in range(n - 2, -1, -1):
                beta[t] = (self.trans_ @ (e[t + 1] * beta[t + 1])) / scale[t + 1]
            gamma = alpha * beta
            gamma /= gamma.sum(axis=1, keepdims=True)
            # expected transitions: sum_t alpha_t (x) A (x) e_{t+1} beta_{t+1} / c_{t+1} (each term sums to 1)
            xi = self.trans_ * (alpha[:-1].T @ (e[1:] * beta[1:] / scale[1:, None]))
            xi += np.eye(self.k) * self.kappa                          # the sticky prior
            self.trans_ = xi / xi.sum(axis=1, keepdims=True)
            w = gamma.sum(axis=0) + 1e-9
            self.means_ = (gamma.T @ Z) / w[:, None]
            self.vars_ = (gamma.T @ Z ** 2) / w[:, None] - self.means_ ** 2 + 1e-3
            self.start_ = gamma[0] + 1e-6
            self.start_ /= self.start_.sum()
        return self

    def stationary(self) -> np.ndarray:
        w, v = np.linalg.eig(self.trans_.T)
        p = np.real(v[:, int(np.argmin(np.abs(w - 1)))])
        p = np.abs(p)
        return p / p.sum()

    def filtered(self, Z: np.ndarray) -> np.ndarray:
        """
        P(state_t | x_1..x_t) for every t (causal). The window starts from the chain's stationary distribution: the
        fitted start_ is the posterior of the TRAINING sequence's first candle, arbitrary for a window cut elsewhere.
        """
        fitted, self.start_ = self.start_, self.stationary()
        try:
            alpha, _, _ = self._forward(self._loglik(Z))
        finally:
            self.start_ = fitted
        return alpha

    def predict(self, Z: np.ndarray) -> np.ndarray:
        return self.filtered(Z).argmax(axis=1)


def stable_names(new_means: np.ndarray, old_means: Optional[np.ndarray], old_names: Dict[int, str],
                 name_of, max_dist2: float = 2.25) -> Dict[int, str]:
    """
    Regime names that survive a refit (ML_PLAN.md C2): the new states are matched to the previous model's states by
    their standardized centers (Hungarian assignment) and inherit their names VERBATIM (suffix included) when the
    center moved less than sqrt(max_dist2) standardized units; other states are named from their centers. A name
    already taken gets the next free numeric suffix (two states never share one name).
    """
    names: Dict[int, str] = {}
    if old_means is not None and len(old_names) and old_means.shape[1] == new_means.shape[1]:
        from scipy.optimize import linear_sum_assignment
        cost = ((new_means[:, None, :] - old_means[None, :, :]) ** 2).sum(axis=2)
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols):
            if int(c) in old_names and cost[r, c] <= max_dist2:
                names[int(r)] = old_names[int(c)]
    taken = set(names.values())
    for i in range(len(new_means)):
        if i in names:
            continue
        base, k, name = name_of(new_means[i]), 1, None
        name = base
        while name in taken:
            k += 1
            name = f"{base}#{k}"
        names[i] = name
        taken.add(name)
    return names


class RegimeModel:
    FEATURES = ('btc_ret_1h', 'btc_vol', 'breadth_1h', 'funding', 'oi_change_1h', 'rvol')

    def __init__(self):
        self.history: Dict[int, List[float]] = {}
        self.model = None
        self.scaler = None
        self.names: Dict[int, str] = {}
        self.current: Optional[str] = None
        self.current_ts = 0
        self.fitted_at = 0.0       # the mixture is refitted once a day: a refit every 15 min changed what a
                                   # regime name meant (8 names for 4 clusters in the journal), so per-regime stats mixed them

    @staticmethod
    def market_features(futures_all: pl.DataFrame, btc: str = 'BTC/USDT:USDT') -> Dict[int, List[float]]:
        """Market-wide features per closed 15m candle from the heavy pass's futures indicator frame."""
        if futures_all is None or futures_all.is_empty():
            return {}
        df = futures_all.select('symbol', 'timestamp', 'close', 'ret_std', 'predicted_funding', 'oi_change_short', 'rvol')
        df = df.with_columns((pl.col('close') / pl.col('close').shift(4) - 1).over('symbol').alias('ret_1h'))
        market = df.group_by('timestamp').agg(
            (pl.col('ret_1h') > 0).mean().alias('breadth_1h'),
            pl.col('predicted_funding').median().alias('funding'),
            pl.col('oi_change_short').median().alias('oi_change_1h'),
            pl.col('rvol').median().alias('rvol'),
            pl.len().alias('n'),
        )
        coin = df.filter(pl.col('symbol') == btc).select('timestamp', pl.col('ret_1h').alias('btc_ret_1h'),
                                                         pl.col('ret_std').alias('btc_vol'))
        # NaN is not null in Polars (a 0 -> 0 OI change is NaN): both are dropped, GaussianMixture rejects either
        rows = (market.join(coin, on='timestamp', how='inner').filter(pl.col('n') >= 20).drop_nulls()
                .filter(pl.all_horizontal([pl.col(f).is_finite() for f in RegimeModel.FEATURES])).sort('timestamp'))
        return {int(r['timestamp']): [float(r[f]) for f in RegimeModel.FEATURES] for r in rows.iter_rows(named=True)}

    def update(self, futures_all: pl.DataFrame) -> Optional[str]:
        """Merge the latest market features, refit the mixture (cheap) and label the newest candle."""
        cfg = CONFIG.ml
        self.history.update(self.market_features(futures_all))
        if len(self.history) > cfg.regime_history:
            for ts in sorted(self.history)[:len(self.history) - cfg.regime_history]:
                del self.history[ts]
        if len(self.history) < cfg.regime_min_history:
            return self.current
        if self.model is None or time.time() - self.fitted_at >= cfg.regime_refit_sec:
            return self.refit()
        return self._label_newest()

    def _label_newest(self) -> Optional[str]:
        """The current model's regime of the newest candle (between the daily refits)."""
        ts = max(self.history)
        if isinstance(self.model, StickyHMM):
            # the filtered state needs the sequence: the last day of candles (the filter forgets older ones)
            stamps = sorted(self.history)[-96:]
            z = self.scaler.transform(np.asarray([self.history[t] for t in stamps]))
            self.current, self.current_ts = self.names[int(self.model.predict(z)[-1])], ts
            return self.current
        z = self.scaler.transform(np.asarray([self.history[ts]]))
        self.current, self.current_ts = self.names[int(self.model.predict(z)[0])], ts
        return self.current

    @staticmethod
    def _new_model(k: int):
        """CONFIG.ml.regime_model: 'gmm' (GaussianMixture, each candle on its own) or 'hmm' (StickyHMM)."""
        cfg = CONFIG.ml
        if cfg.regime_model == 'hmm':
            return StickyHMM(k, cfg.regime_sticky_kappa)
        from sklearn.mixture import GaussianMixture
        return GaussianMixture(n_components=k, covariance_type='full', random_state=0, reg_covar=1e-3)

    def refit(self) -> Optional[str]:
        """Fit the model on the whole history (pretrained months + live candles) and label its newest candle."""
        from sklearn.preprocessing import StandardScaler
        cfg = CONFIG.ml
        stamps = sorted(self.history)
        X = np.asarray([self.history[t] for t in stamps])
        scaler = StandardScaler().fit(X)
        Z = scaler.transform(X)
        k = min(cfg.regime_clusters, max(2, len(X) // 25))
        # the HMM's EM walks the sequence in Python: fit on the recent candles only (it runs in a thread next to
        # the event loop, and pure-Python loops take the GIL from it)
        fit_z = Z[-cfg.regime_hmm_fit_candles:] if cfg.regime_model == 'hmm' else Z
        model = self._new_model(k).fit(fit_z)
        old = self.model.means_ if self.model is not None and self.scaler is not None else None
        if old is not None:
            # the previous centers in the NEW scaler's units (the scaler moves with the history)
            old = scaler.transform(self.scaler.inverse_transform(old))
        names = stable_names(model.means_, old, self.names, self._name)
        label = int(model.predict(Z[-96:])[-1]) if cfg.regime_model == 'hmm' else int(model.predict(Z[-1:])[0])
        self.model, self.scaler, self.names = model, scaler, names
        self.current, self.current_ts = names[label], stamps[-1]
        self.fitted_at = time.time()
        return self.current

    def labels_walk_forward(self, step_ms: int = 7 * 86_400_000) -> Dict[int, str]:
        """
        Regime of every history candle as known at its time: each step is labelled by a mixture fitted only on the
        candles before it (pretraining must not label the past with a model that has seen the future).
        """
        from sklearn.preprocessing import StandardScaler
        cfg = CONFIG.ml
        stamps = sorted(self.history)
        out: Dict[int, str] = {}
        prev_means, prev_scaler, prev_names = None, None, {}
        if len(stamps) < cfg.regime_min_history:
            return out
        X = np.asarray([self.history[t] for t in stamps])
        t0 = stamps[0] + step_ms
        i = int(np.searchsorted(stamps, t0))
        while i < len(stamps):
            j = int(np.searchsorted(stamps, stamps[i] + step_ms))
            past = X[:i]
            if len(past) >= cfg.regime_min_history:
                scaler = StandardScaler().fit(past)
                k = min(cfg.regime_clusters, max(2, len(past) // 25))
                zp = scaler.transform(past)
                model = self._new_model(k).fit(zp[-cfg.regime_hmm_fit_candles:] if cfg.regime_model == 'hmm' else zp)
                old = scaler.transform(prev_scaler.inverse_transform(prev_means)) if prev_means is not None else None
                names = stable_names(model.means_, old, prev_names, self._name)
                prev_means, prev_scaler, prev_names = model.means_, scaler, names
                if isinstance(model, StickyHMM):
                    # filter through the past into the step: the state at t uses x_1..x_t only
                    lab = model.predict(scaler.transform(X[max(0, i - 96):j]))[-(j - i):]
                else:
                    lab = model.predict(scaler.transform(X[i:j]))
                for t, k2 in zip(stamps[i:j], lab):
                    out[t] = names[int(k2)]
            i = j
        return out

    def label_history(self) -> Dict[int, str]:
        """The fitted model's regime of every candle in the history (pretraining labels its journal rows with it)."""
        if self.model is None or not self.history:
            return {}
        stamps = sorted(self.history)
        labels = self.model.predict(self.scaler.transform(np.asarray([self.history[t] for t in stamps])))
        return {t: self.names[int(k)] for t, k in zip(stamps, labels)}     # HMM: filtered (causal) states

    @staticmethod
    def _name(center: np.ndarray) -> str:
        """Name a cluster from its standardized center: direction from BTC 1h move + breadth, then volatility."""
        z = dict(zip(RegimeModel.FEATURES, center))
        trend = (z['btc_ret_1h'] + z['breadth_1h']) / 2
        direction = 'up' if trend > 0.5 else 'down' if trend < -0.5 else 'flat'
        vol = 'volatile' if z['btc_vol'] > 0.5 or z['rvol'] > 0.75 else 'quiet' if z['btc_vol'] < -0.5 else 'normal'
        return f"{direction}·{vol}"

    def state(self) -> Dict:
        return {'history': self.history}

    def load_state(self, state: Dict):
        for ts, values in (state or {}).get('history', {}).items():
            if len(values) == len(self.FEATURES):
                self.history[int(ts)] = list(values)


# ====================================================================== 3. P(edge)

class SuccessModel:
    """Online logistic regression on journal features, reset on drift (ADWIN over its 0/1 errors)."""

    NUMERIC = ('long_score', 'short_score', 'rvol_1m', 'price_z', 'oi_z', 'whale_net_5m', 'funding_8h',
               'top_venue_share', 'depth_imb', 'top_ratio', 'ml_score')

    def __init__(self):
        self.lock = threading.Lock()
        self.drifts = 0
        self._prior: Optional[bytes] = None      # the pretrained model (pretrain.py): the start and the drift reset
        self._new()

    def _new(self):
        from river import compose, drift, linear_model, optim, preprocessing
        self.model = compose.Pipeline(preprocessing.StandardScaler(),
                                      linear_model.LogisticRegression(optimizer=optim.SGD(0.02), l2=1e-3))
        self.detector = drift.ADWIN()
        self.n = 0
        self.correct = 0

    @staticmethod
    def features(row) -> Dict[str, float]:
        """Features from a journal row (dict or sqlite3.Row): the same columns live and on replay."""
        get = (lambda k: row[k] if k in row.keys() else None) if hasattr(row, 'keys') else row.get
        x: Dict[str, float] = {}
        for key in SuccessModel.NUMERIC:
            value = get(key)
            if value is not None:
                x[key] = float(value)
        direction = get('direction') or 0
        x['direction'] = float(direction)
        # The same readings in the signal's direction (a linear model cannot learn "whales buying helps a long and hurts
        # a short" from the raw sign alone)
        for key in ('whale_net_5m', 'price_z', 'oi_z', 'depth_imb', 'mkt_1h', 'mkt_4h', 'btc_1h', 'coin_trend'):
            value = get(key)
            if value is not None and direction:
                x[key + '_dir'] = float(value) * direction
        for key in ('spot_delta_1h', 'perp_delta_1h'):
            value = get(key)
            if value is not None:
                x[key + '_sign'] = float(np.sign(value) * direction)
        if get('vol_ratio') is not None:
            x['vol_ratio'] = float(get('vol_ratio'))
        # the weekly trend in the signal's direction (clipped: a fresh listing's first weeks give |z| of 10+) and the
        # market's weekly breadth around its middle, in the signal's direction
        if get('trend_w') is not None and direction:
            x['trend_w_dir'] = max(-5.0, min(5.0, float(get('trend_w')))) * direction
        if get('breadth_w') is not None and direction:
            x['breadth_w_dir'] = (float(get('breadth_w')) - 0.5) * direction
        if get('volume_24h'):
            x['volume_24h_log'] = math.log10(float(get('volume_24h')))
        # entry confirmations (strategies/confirm.py): +1 present, -1 absent, missing = no reading
        confirms = get('confirms')
        if isinstance(confirms, str):
            confirms = json.loads(confirms)
        for name, value in (confirms or {}).items():
            if not name.startswith('_') and value is not None and value != 'n/a':
                x[f'confirm_{name}'] = 1.0 if value is True or isinstance(value, str) else -1.0
        if get('strategy'):
            x[f"strategy={get('strategy')}"] = 1.0
        crowd = get('market_crowd')
        if crowd is not None:
            x['market_crowd_log'] = math.log1p(float(crowd))
        liq = (get('liq_long_5m') or 0.0) + (get('liq_short_5m') or 0.0)
        x['liq_log'] = math.log1p(liq)
        # Directional readings in the signal's direction (a linear model cannot learn "crowded longs hurt a long,
        # help a short" from the raw value): funding (all venues, else Binance), long/short ratios (log), the
        # tracked Hyperliquid accounts, the Coinbase premium, which side was liquidated
        if direction:
            funding = get('agg_funding_8h') if get('agg_funding_8h') is not None else get('funding_8h')
            if funding is not None:
                x['funding_dir'] = float(funding) * 1e4 * direction
            for key in ('top_ratio', 'ls_global', 'ls_top', 'ls_bybit', 'ls_okx'):
                value = get(key)
                if value and value > 0:
                    x[key + '_dir'] = math.log(float(value)) * direction
            hl = get('hl_net_usd')
            if hl is not None:
                x['hl_net_dir'] = math.copysign(math.log1p(abs(float(hl)) / 1e5), float(hl)) * direction
            premium = get('cb_premium')
            if premium is not None:
                x['cb_premium_dir'] = float(premium) * 1e4 * direction
            x['liq_net_dir'] = (math.log1p(get('liq_short_5m') or 0.0) - math.log1p(get('liq_long_5m') or 0.0)) * direction
        ts = get('ts_ms')
        if ts:
            hour = (int(ts) // 3_600_000) % 24
            x['hour_sin'], x['hour_cos'] = math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24)
            x['weekend'] = 1.0 if (int(ts) // 86_400_000 + 3) % 7 >= 5 else 0.0      # Monday = 0 (1970-01-01 was a Thursday)
        x['perp_led'] = float(get('perp_led') or 0)
        x['cluster_dir'] = float((get('cluster') or 0) * direction)
        x['early_quarter'] = 1.0 if (get('sec_into_candle') or 0) < 60 else 0.0
        x[f"setup={get('group_key')}"] = 1.0
        if get('regime'):
            x[f"regime={get('regime')}"] = 1.0
        return x

    def predict(self, row) -> Optional[float]:
        x = self.features(row)
        with self.lock:
            if self.n == 0:
                return None
            return float(self.model.predict_proba_one(x).get(True, 0.5))

    def learn(self, row, label: bool):
        x = self.features(row)
        with self.lock:
            if self.n:
                p = self.model.predict_proba_one(x).get(True, 0.5)
                error = int((p >= 0.5) != label)
                self.correct += 1 - error
                self.detector.update(error)
                if self.detector.drift_detected:
                    self.drifts += 1
                    logger.info(f"ML P(edge): error drift detected after {self.n} rows, back to "
                                f"{'the pretrained model' if self._prior else 'an empty model'}")
                    self._restore_prior() if self._prior else self._new()
            self.model.learn_one(x, label)
            self.n += 1

    def state(self) -> Dict:
        """The picklable model (pretrain.py saves it; the lock is not part of it)."""
        with self.lock:
            return {'model': self.model, 'n': self.n, 'correct': self.correct, 'drifts': self.drifts}

    def load_pretrained(self, state: Dict):
        """Start from the pretrained model; live rows keep training it, an error drift returns to it."""
        import pickle
        self._prior = pickle.dumps({'model': state['model'], 'n': state['n'], 'correct': state['correct']})
        with self.lock:
            self._restore_prior()

    def _restore_prior(self):
        import pickle
        from river import drift
        prior = pickle.loads(self._prior)
        self.model, self.n, self.correct = prior['model'], prior['n'], prior['correct']
        self.detector = drift.ADWIN()

    @property
    def mature(self) -> bool:
        return self.n >= CONFIG.ml.success_min_trained

    @property
    def accuracy(self) -> Optional[float]:
        return self.correct / (self.n - 1) if self.n > 1 else None


def label_of(row, baseline: Optional[float]) -> Optional[bool]:
    """Positive = the 4h return in the signal's direction beat the universe median over the same window."""
    ret = row['ret_4h']
    direction = row['direction']
    if ret is None or not direction or baseline is None:
        return None
    return direction * (ret - baseline) > 0
