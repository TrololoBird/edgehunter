"""
Where the bot's memory sits, cheap enough for the live loop (tracemalloc / objgraph walk every object and froze it:
2026-10-05, 72s stalls at 1.8 GB).

- `process_breakdown()`: this process's committed memory by region class (Windows VirtualQuery, the VMMap view):
  pymalloc arenas (1 MB blocks = Python objects), large private blocks (numpy / polars buffers, allocator segments),
  images (DLL code). tools/vmmap.py prints the same for another process from outside.
- `structures(fetcher, scanner)`: sizes of the bot's own containers, polars `estimated_size`, numpy `nbytes`, Python
  containers estimated from a sample of their elements; `MarketData` fields summed over all coins.
"""
import array
import ctypes
import sys
import time
from collections import Counter, deque
from typing import Dict, List, Tuple

import numpy as np

try:
    import polars as pl
except ImportError:      # pragma: no cover
    pl = None

SAMPLE = 40
MAX_DEPTH = 5


# ---------------------------------------------------------------------- process (Windows)

class _MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', ctypes.c_uint32), ('PartitionId', ctypes.c_uint16),
                ('RegionSize', ctypes.c_size_t), ('State', ctypes.c_uint32), ('Protect', ctypes.c_uint32),
                ('Type', ctypes.c_uint32)]


MEM_COMMIT, MEM_PRIVATE, MEM_IMAGE = 0x1000, 0x20000, 0x1000000
ARENA = 1 << 20


def regions(pid: int = 0) -> Tuple[Dict[int, int], int, int]:
    """({allocation base: committed private bytes}, image bytes, mapped bytes) of a process (0 = this one)."""
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.VirtualQueryEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
    k.VirtualQueryEx.restype = ctypes.c_size_t
    k.OpenProcess.restype = ctypes.c_void_p
    k.GetCurrentProcess.restype = ctypes.c_void_p
    handle = k.OpenProcess(0x0400 | 0x0010, False, pid) if pid else k.GetCurrentProcess()
    if not handle:
        raise OSError(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}")
    alloc: Dict[int, int] = {}
    image = mapped = addr = 0
    m = _MBI()
    try:
        while addr < 0x7FFFFFFFFFFF and k.VirtualQueryEx(handle, addr, ctypes.byref(m), ctypes.sizeof(m)):
            if m.State == MEM_COMMIT:
                if m.Type == MEM_PRIVATE:
                    base = m.AllocationBase or 0
                    alloc[base] = alloc.get(base, 0) + m.RegionSize
                elif m.Type == MEM_IMAGE:
                    image += m.RegionSize
                else:
                    mapped += m.RegionSize
            addr = (m.BaseAddress or 0) + m.RegionSize
    finally:
        if pid:
            k.CloseHandle(ctypes.c_void_p(handle))
    return alloc, image, mapped


def process_breakdown(pid: int = 0) -> Dict[str, float]:
    """MB by class: private, arenas (pymalloc 1 MB blocks), small (< 1 MB), mid (1-8 MB), large (>= 8 MB), image."""
    if sys.platform != 'win32':
        return {}
    alloc, image, mapped = regions(pid)
    out = Counter()
    for size in alloc.values():
        out['private'] += size
        if size == ARENA:
            out['arenas'] += size
        elif size < ARENA:
            out['small'] += size
        elif size < 8 * ARENA:
            out['mid'] += size
        else:
            out['large'] += size
    out['image'], out['mapped'] = image, mapped
    return {k: v / 2 ** 20 for k, v in out.items()}


# ---------------------------------------------------------------------- the bot's own structures

def approx_size(obj, depth: int = 0, seen=None) -> int:
    """Bytes held by obj: exact for polars / numpy / array, estimated from a sample for Python containers."""
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return 0
    seen.add(id(obj))
    if pl is not None and isinstance(obj, (pl.DataFrame, pl.Series)):
        return int(obj.estimated_size())
    if isinstance(obj, np.ndarray):
        return int(obj.nbytes)
    if isinstance(obj, array.array):
        return obj.itemsize * len(obj)
    if isinstance(obj, (str, bytes, bytearray, int, float, bool)) or obj is None:
        return sys.getsizeof(obj)
    base = sys.getsizeof(obj)
    if depth >= MAX_DEPTH:
        return base
    k = _sample_size(depth)
    if isinstance(obj, dict):
        items = list(obj.items()) if len(obj) <= k else _sample(list(obj.items()), k)
        part = sum(approx_size(k, depth + 1, seen) + approx_size(v, depth + 1, seen) for k, v in items)
        return base + _scale(part, len(items), len(obj))
    if isinstance(obj, (list, tuple, deque, set, frozenset)):
        seq = list(obj)
        items = seq if len(seq) <= k else _sample(seq, k)
        part = sum(approx_size(v, depth + 1, seen) for v in items)
        return base + _scale(part, len(items), len(seq))
    fields = getattr(obj, '__dict__', None)
    if fields is None and hasattr(obj, '__slots__'):
        fields = {s: getattr(obj, s, None) for s in obj.__slots__}
    if fields:
        return base + sum(approx_size(v, depth + 1, seen) for v in fields.values())
    return base


def _sample_size(depth: int) -> int:
    """40 elements at the top, fewer deeper: a sample of a sample stays bounded (40 x 10 x 3 x 3 x 3 calls)."""
    return max(3, SAMPLE >> (2 * depth))


def _sample(seq: list, k: int) -> list:
    step = max(1, len(seq) // k)
    return seq[::step][:k]


def _scale(part: int, sampled: int, total: int) -> int:
    return int(part * total / sampled) if sampled else 0


def structures(fetcher, scanner) -> List[Tuple[str, float]]:
    """
    [(name, MB)] largest first: MarketData fields summed over coins, then every attribute of the fetcher / scanner.
    One `seen` set across all of them: an object shared by several owners (the markets, symbol maps, the fetcher
    itself) is counted once, for the first owner.
    """
    out: Counter = Counter()
    markets = getattr(fetcher, 'markets', {}) or {}
    seen = {id(fetcher), id(scanner), id(markets)}
    mds = list(markets.values())
    seen.update(id(md) for md in mds)
    for md in mds:
        for name, value in list(vars(md).items()):
            out[f"md.{name}"] += approx_size(value, 0, seen)
    for prefix, root in (('fetcher', fetcher), ('scanner', scanner)):
        for name, value in list(vars(root).items()):
            if callable(value):
                continue
            out[f"{prefix}.{name}"] += approx_size(value, 0, seen)
    return [(k, v / 2 ** 20) for k, v in out.most_common()]


def report(fetcher, scanner, top: int = 12) -> str:
    t0 = time.perf_counter()
    proc = process_breakdown()
    parts = structures(fetcher, scanner)
    known = sum(mb for _, mb in parts)
    proc_text = ', '.join(f"{k} {proc[k]:.0f}" for k in ('private', 'arenas', 'large', 'mid', 'small', 'image')
                          if k in proc)
    top_text = ', '.join(f"{k} {mb:.0f}" for k, mb in parts[:top] if mb >= 1)
    return (f"Memory MB: {proc_text} | structures ~{known:.0f}: {top_text} "
            f"({(time.perf_counter() - t0) * 1000:.0f} ms)")
