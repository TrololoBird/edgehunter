"""
Per-coin result cache of the long archive replays (research_cards / research_maniac / research_classic): each coin's
rows are saved as soon as its worker returns, and a restarted run skips the coins already done. The cloud worker
was restarted once mid-run (2026-10-02) and 125 coins of research_cards were lost.
"""
import hashlib
import os
import pickle
from typing import Any, Optional

_ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_ROOT = os.path.join(_ROOT, 'research_cache')


def run_dir(script: str, *key_parts) -> str:
    """A directory per run configuration (script + window + options + logic version + pierce model)."""
    import glob
    from config import CONFIG
    # the code that produces the rows: a research-script or strategy edit without a logic_version bump must not reuse
    # stale per-coin results
    src = hashlib.sha1()
    for f in sorted(glob.glob(os.path.join(_ROOT, 'strategies', '*.py')) +
                    [os.path.join(_ROOT, n) for n in (f"research_{script}.py", 'research_cards.py', 'levels.py',
                                                      'zones.py', 'pierce.py', 'indicators.py', 'scorer.py')]):
        if os.path.exists(f):
            with open(f, 'rb') as fh:
                src.update(fh.read())
    tag = '|'.join(map(str, key_parts + (CONFIG.journal.logic_version, os.environ.get('PIERCE_MODEL', ''),
                                         os.environ.get('RESEARCH_ENTRY', ''), src.hexdigest())))
    d = os.path.join(CACHE_ROOT, f"{script}_{hashlib.sha1(tag.encode()).hexdigest()[:10]}")
    os.makedirs(d, exist_ok=True)
    return d


def _path(d: str, coin: str) -> str:
    return os.path.join(d, coin.replace('/', '_').replace(':', '_') + '.pkl')


def load(d: str, coin: str) -> Optional[Any]:
    p = _path(d, coin)
    if not os.path.exists(p):
        return None
    try:
        with open(p, 'rb') as fh:
            return pickle.load(fh)          # our own file, written by save() below
    except (OSError, EOFError, pickle.UnpicklingError):
        return None


def save(d: str, coin: str, result: Any):
    p = _path(d, coin)
    with open(p + '.tmp', 'wb') as fh:
        pickle.dump(result, fh)
    os.replace(p + '.tmp', p)
