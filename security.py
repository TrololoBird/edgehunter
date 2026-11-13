"""Small fail-closed helpers for external URLs and local model artifacts."""

import os
import pickle
import stat
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def safe_urlopen(request: str | urllib.request.Request, *, timeout: float):
    """Open only HTTPS resources with an explicit timeout."""
    url = request if isinstance(request, str) else request.full_url
    if urllib.parse.urlparse(url).scheme.lower() != "https":
        raise ValueError(f"only https URLs are permitted: {url!r}")
    return urllib.request.urlopen(request, timeout=timeout)


def safe_pickle_load(path: str, allowed_root: str) -> Any:
    """Load a model only from a regular, owner-only local file."""
    target = Path(path).resolve(strict=True)
    root = Path(allowed_root).resolve()
    if root not in target.parents:
        raise ValueError(f"model is outside the allowed directory: {target}")
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise PermissionError(f"model must be a regular owner-only file: {target}")
    if info.st_uid != os.getuid():
        raise PermissionError(f"model is not owned by the current user: {target}")
    with target.open("rb") as fh:
        return pickle.load(fh)
