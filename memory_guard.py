"""Cheap cgroup-v2 memory pressure checks; never walks Python objects."""
from pathlib import Path


def _read(name: str):
    for base in (Path('/sys/fs/cgroup'), Path('/sys/fs/cgroup/system.slice/edgehunter-bot.service')):
        p = base / name
        try:
            return int(p.read_text().strip())
        except (FileNotFoundError, ValueError, PermissionError):
            continue
    return None


def snapshot() -> dict:
    return {'current': _read('memory.current'), 'high': _read('memory.high'), 'max': _read('memory.max')}


def pressured(ratio: float = 0.90) -> bool:
    s = snapshot()
    current, limit = s['current'], s['high']
    return bool(current and limit and limit > 0 and current >= limit * ratio)
