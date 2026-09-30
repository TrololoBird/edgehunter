"""
Event-loop watchdog: finds WHAT blocks the loop instead of only reporting that it was blocked.

A coroutine touches a heartbeat every 100ms; a daemon thread checks it. When the loop has not ticked for
`stall_sec`, the thread samples the main thread's stack (sys._current_frames) a few times during the stall and
logs the most frequent innermost frames of our code. Garbage-collection pauses are timed through gc.callbacks
(a full collection over hundreds of MB of live objects also stops the loop) and reported with the stall.
"""
import asyncio
import gc
import logging
import sys
import threading
import time
import traceback
from collections import Counter
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def exit_with_parent(parent_pid: int) -> None:
    """
    ProcessPoolExecutor initializer: the worker ignores console Ctrl+C / Ctrl+Break and exits when the bot's process
    is gone. A bot killed without its
    shutdown (console closed, crash, Stop-Process) left its spawn workers running for days (5 orphans measured).
    """
    import os
    import signal

    # Ctrl+C goes to every process of the console: a worker killed by it mid-job made the bot's graceful shutdown
    # log "process pool terminated abruptly". The bot shuts its pools down itself.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)

    def watch():
        if sys.platform == 'win32':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x00100000, False, parent_pid)   # SYNCHRONIZE
            if handle:
                kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)            # INFINITE
        else:
            while os.getppid() == parent_pid:
                time.sleep(2)
        os._exit(0)

    threading.Thread(target=watch, name='exit-with-parent', daemon=True).start()


def free_ram_mb() -> Optional[float]:
    """
    Available physical memory (Windows). Stalls whose loop samples sit in C code (`main.py <module>`, ssl reads) with
    no busy thread are usually the machine paging the bot out (6 GB shared with Claude and Chrome; measured
    2026-09-30: ~800 MB free, 3-5k pages/s, the bot's working set trimmed to 197 of 580 MB): shown with each stall.
    """
    if sys.platform != 'win32':
        return None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullAvailPhys / 2 ** 20
    except Exception:
        pass
    return None


class LoopWatchdog:
    IDLE_FUNCTIONS = {'wait', '_exhaustive_wait', 'get', 'select', 'accept', 'recv', 'recv_bytes', '_recv_bytes',
                      'poll', 'sleep', 'acquire', 'read',
                      '_worker'}   # an idle ThreadPoolExecutor worker sits in the C SimpleQueue.get under _worker
    def __init__(self, stall_sec: float = 0.5, report_sec: float = 1.0):
        self.stall_sec = stall_sec
        self.report_sec = report_sec
        self.beat = time.monotonic()
        self.main_ident = threading.main_thread().ident
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._gc_start = 0.0
        self.gc_pauses: list = []       # (end monotonic, seconds, generation)
        # Reports start once market data flows (arm()): before the streams are up a slow loop delays nothing
        self.armed = False

    # ---------------------------------------------------------------- gc timing

    def _gc_callback(self, phase: str, info: dict):
        if phase == 'start':
            self._gc_start = time.perf_counter()
        elif self._gc_start:
            took = time.perf_counter() - self._gc_start
            if took >= 0.1:
                self.gc_pauses.append((time.monotonic(), took, info.get('generation')))
                del self.gc_pauses[:-20]

    # ---------------------------------------------------------------- lifecycle

    async def heartbeat(self):
        while True:
            self.beat = time.monotonic()
            await asyncio.sleep(0.1)

    def start(self):
        self.beat = time.monotonic()
        gc.callbacks.append(self._gc_callback)
        self._thread = threading.Thread(target=self._watch, name='loop-watchdog', daemon=True)
        self._thread.start()

    def arm(self):
        self.armed = True

    def stop(self):
        self._stop.set()
        if self._gc_callback in gc.callbacks:
            gc.callbacks.remove(self._gc_callback)

    # ---------------------------------------------------------------- watching

    @staticmethod
    def _describe(frame) -> str:
        stack = traceback.extract_stack(frame)
        ours = [f for f in stack if 'site-packages' not in f.filename and 'lib' + '\\' + 'asyncio' not in f.filename.lower()]
        picked = (ours or stack)[-3:]
        return ' <- '.join(f"{f.filename.rsplit(chr(92), 1)[-1]}:{f.lineno} {f.name}" for f in reversed(picked))

    def _sample(self) -> Tuple[Optional[str], List[str]]:
        """The main thread's innermost own frames, and what the other busy threads are running (GIL holders)."""
        frames = sys._current_frames()
        main = frames.get(self.main_ident)
        others = []
        for ident, frame in frames.items():
            if ident in (self.main_ident, threading.get_ident()):
                continue
            # Threads blocked in a wait (idle pool workers, the process pool's feeder / manager threads) hold no GIL
            if traceback.extract_stack(frame)[-1].name in self.IDLE_FUNCTIONS:
                continue
            others.append(self._describe(frame))
        return (self._describe(main) if main is not None else None), others

    def _watch(self):
        while not self._stop.wait(0.05):
            stalled = time.monotonic() - self.beat
            if stalled < self.stall_sec:
                continue
            started = self.beat
            samples: Counter = Counter()
            workers: Counter = Counter()
            while self.beat == started and not self._stop.is_set():
                main, others = self._sample()
                if main:
                    samples[main] += 1
                for where in others:
                    workers[where] += 1
                time.sleep(0.05)
            total = time.monotonic() - started
            if total < self.report_sec or not self.armed:
                continue
            gc_part = [(took, gen) for end, took, gen in self.gc_pauses if end >= started]
            gc_text = f"; gc {sum(t for t, _ in gc_part):.1f}s (gen {max(g for _, g in gc_part)})" if gc_part else ''
            where = '; '.join(f"{n}x {s}" for s, n in samples.most_common(3)) or 'no sample'
            busy = '; '.join(f"{n}x {s}" for s, n in workers.most_common(3))
            free = free_ram_mb()
            ram_text = f"; RAM free {free:.0f} MB" if free is not None else ''
            logger.warning(f"Event loop blocked {total:.1f}s{gc_text}{ram_text} | loop: {where}" + (f" | threads: {busy}" if busy else ''))
