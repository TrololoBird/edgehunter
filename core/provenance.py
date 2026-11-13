"""Immutable process provenance captured once at import time.

The service must be able to distinguish rows written by the code loaded in a
running process from later edits made on disk.  Deployment may provide the
values explicitly; the git fallback is only for local runs and never blocks
startup when the checkout metadata is unavailable.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ['git', *args], stderr=subprocess.DEVNULL, text=True,
            cwd=Path(__file__).resolve().parents[1], timeout=1,
        ).strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _implementation_hash() -> str | None:
    root = Path(__file__).resolve().parents[1]
    try:
        digest = hashlib.sha256()
        for name in ('main.py', 'config.py', 'scanner.py', 'signal_book.py', 'executor.py', 'journal.py'):
            path = root / name
            digest.update(name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()[:16]
    except OSError:
        return None


SOURCE_COMMIT = os.environ.get('EDGEHUNTER_SOURCE_COMMIT') or _git('rev-parse', 'HEAD')
SOURCE_DIRTY = bool(os.environ.get('EDGEHUNTER_SOURCE_DIRTY')) or bool(_git('status', '--porcelain'))
IMPLEMENTATION_HASH = os.environ.get('EDGEHUNTER_IMPLEMENTATION_HASH') or _implementation_hash()


def fields() -> dict[str, object]:
    return {
        'source_commit': SOURCE_COMMIT,
        'implementation_hash': IMPLEMENTATION_HASH,
        'source_dirty': int(SOURCE_DIRTY),
    }
