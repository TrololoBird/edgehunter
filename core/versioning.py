"""Comparable EdgeHunter logic-version helpers."""
from __future__ import annotations
import re
from typing import Optional, Tuple

_VERSION = re.compile(r"^eng-(?P<number>\d+)(?P<release>[a-z]*)$")

def version_key(value: Optional[str]) -> Tuple[int, str]:
    match = _VERSION.fullmatch(str(value or "").strip().lower())
    return (int(match.group("number")), match.group("release")) if match else (0, "")

def version_no(value: Optional[str]) -> int:
    """Return the numeric family while accepting lettered releases (eng-169l/m)."""
    return version_key(value)[0]

def same_version(left: Optional[str], right: Optional[str]) -> bool:
    """Exact release equality for journal/statistics partitions."""
    return bool(left and right and str(left).strip().lower() == str(right).strip().lower())
