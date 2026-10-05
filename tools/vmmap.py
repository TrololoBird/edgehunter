r"""Committed memory of a running process by region class, read from outside (no injection, no slowdown).

    .venv\Scripts\python tools\vmmap.py <pid>      # e.g. the bot's interpreter (the larger of the two main.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from memreport import regions, process_breakdown   # noqa: E402

if __name__ == '__main__':
    pid = int(sys.argv[1])
    for k, v in process_breakdown(pid).items():
        print(f"{k:8s} {v:8.0f} MB")
    alloc, _, _ = regions(pid)
    print("largest private allocations (MB):",
          ', '.join(f"{v / 2**20:.0f}" for v in sorted(alloc.values(), reverse=True)[:20]))
