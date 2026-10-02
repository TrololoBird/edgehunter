"""
Model cards and feature drift (ML_PLAN.md H1 / H2).

- A card (models/cards/<name>.json) sits next to every trained model: the data window, logic_version, the features
  with their reference distribution (decile edges + shares, from the training rows), out-of-sample metrics, the
  commit and the time. `card_ok` says whether a model may be used by the current logic.
- Drift: the population stability index of each feature's live values against the card's reference
  (PSI < 0.1 stable, 0.1-0.25 moderate, > 0.25 the model sees a population it was not trained on). The journal
  refreshes it hourly (`SignalJournal.refresh_drift`) and the Health line prints the worst feature.
"""
import json
import logging
import os
import subprocess
import time
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)
_ROOT = os.path.dirname(os.path.abspath(__file__))
CARDS_DIR = os.path.join(_ROOT, 'models', 'cards')
DRIFT: Dict[str, float] = {}           # feature -> PSI of the live window vs the card (refresh_drift)


def _commit() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, cwd=_ROOT,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def reference(values: Iterable[float], bins: int = 10) -> Optional[Dict]:
    """Decile edges and the share in each bin of a feature's training values (None if too few / constant)."""
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if len(v) < 200:
        return None
    edges = np.unique(np.quantile(v, np.linspace(0, 1, bins + 1)[1:-1]))
    if not len(edges):
        return None
    counts = np.bincount(np.searchsorted(edges, v, side='right'), minlength=len(edges) + 1)
    return {'edges': edges.tolist(), 'shares': (counts / counts.sum()).tolist(), 'n': int(len(v))}


def psi(ref: Dict, values: Sequence[float]) -> Optional[float]:
    """Population stability index of `values` against a reference from `reference` (None under 50 values)."""
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if len(v) < 50:
        return None
    edges = np.asarray(ref['edges'])
    exp = np.asarray(ref['shares'])
    act = np.bincount(np.searchsorted(edges, v, side='right'), minlength=len(edges) + 1) / len(v)
    exp, act = np.clip(exp, 1e-4, None), np.clip(act, 1e-4, None)
    return float(np.sum((act - exp) * np.log(act / exp)))


def write_card(name: str, model_path: str, window: str, metrics: Optional[Dict] = None,
               features: Optional[Dict[str, Dict]] = None, notes: str = '') -> str:
    from config import CONFIG
    os.makedirs(CARDS_DIR, exist_ok=True)
    card = {'name': name, 'model_path': os.path.relpath(model_path, _ROOT) if os.path.isabs(model_path) else model_path,
            'logic_version': CONFIG.journal.logic_version, 'window': window, 'created': time.time(),
            'commit': _commit(), 'metrics': metrics or {}, 'features': features or {}, 'notes': notes}
    path = os.path.join(CARDS_DIR, f"{name}.json")
    with open(path + '.tmp', 'w', encoding='utf-8') as fh:
        json.dump(card, fh, indent=1)
    os.replace(path + '.tmp', path)
    return path


def load_card(name: str) -> Optional[Dict]:
    path = os.path.join(CARDS_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        logger.warning(f"model card {name} unreadable ({type(e).__name__} {e})")
        return None


def card_ok(name: str, require: bool = False) -> bool:
    """A model may be used: its card exists (when `require`) and was written by the current logic_version."""
    from config import CONFIG
    card = load_card(name)
    if card is None:
        if require:
            logger.warning(f"model {name}: no card in models/cards - not used")
        return not require
    if card.get('logic_version') != CONFIG.journal.logic_version:
        logger.warning(f"model {name}: card of logic {card.get('logic_version')}, bot runs "
                       f"{CONFIG.journal.logic_version} - not used")
        return False
    return True


def feature_references(rows: List[Dict], keys: Optional[Iterable[str]] = None) -> Dict[str, Dict]:
    """Reference distributions of every numeric feature present in `rows` (dicts of feature -> value)."""
    keys = list(keys) if keys is not None else sorted({k for r in rows for k in r})
    out = {}
    for k in keys:
        ref = reference(r.get(k) for r in rows)
        if ref:
            out[k] = ref
    return out


def drift_of(card: Dict, rows: List[Dict]) -> Dict[str, float]:
    """PSI per feature of `rows` (live feature dicts) against the card's references."""
    out = {}
    for k, ref in (card.get('features') or {}).items():
        p = psi(ref, [r.get(k) for r in rows])
        if p is not None:
            out[k] = p
    return out


def worst_drift() -> Optional[tuple]:
    if not DRIFT:
        return None
    k = max(DRIFT, key=DRIFT.get)
    return k, DRIFT[k]
