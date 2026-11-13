"""Helpers for SQLite identifiers that cannot be supplied as parameters."""

import re

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def identifier(name: str, allowed: set[str]) -> str:
    """Return a validated SQL identifier or fail closed."""
    if name not in allowed or not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"unsupported SQL identifier: {name!r}")
    return name
