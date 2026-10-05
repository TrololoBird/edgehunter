#!/usr/bin/env python3
"""
Crypto Market Microstructure Scanner (Binance USD-M perpetuals).

- Phases on 15m candles (scorer.py): long = A accumulation / B spring / E capitulation, short = C distribution /
  D breakdown; Tier-0 raw anomalies every 2s (RVOL 1m, OI 5m, price 5m, whale flow).
- Trade model (levels.py + zones.py): the 15m leg gives the context, the coin's level map (support / resistance,
  liquidity pools, liquidation clusters, volume profile, Fibonacci) the zone, stop and targets; the entry is a 5m
  structure shift, confirmed by order flow (flow.py); Binance + Bybit / OKX / Hyperliquid / Bitget / Coinbase
  streams (venues.py).
- Journal (journal.py) records every setup, entry and finished card; `python stats.py` shows how they played out.
- Browser dashboard (webui.py) on http://127.0.0.1:8765; the console shows the log.
Ctrl+C stops gracefully (press again after 3s to force).
"""

import os
# polars' bundled mimalloc kept freed memory committed: 579 MB of large private blocks against ~290 MB of live
# structures (memreport, 2026-10-05). Purge freed pages at once; set before polars loads (the workers inherit it).
os.environ.setdefault('MIMALLOC_PURGE_DELAY', '0')

import argparse
import asyncio
import logging
import errors
import os
import signal
import sys
import time
import queue
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

from config import CONFIG
from journal import SignalJournal
from netstate import NETWORK
from scanner import Scanner

logger = logging.getLogger(__name__)


def setup_logging() -> QueueListener:
    """
    Console + a size-rotated scanner.log (a long run never grows the file without bound), written by a listener
    THREAD: the loop only queues records. A console write blocks while the window has a selection or conhost is
    paged out (measured: the loop stalled 2s inside StreamHandler.emit).
    """
    cfg = CONFIG.logging
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s', datefmt='%H:%M:%S')
    handlers = [logging.StreamHandler(sys.stdout),
                RotatingFileHandler(cfg.file, maxBytes=cfg.max_bytes, backupCount=cfg.backups, encoding='utf-8')]
    for handler in handlers:
        handler.setFormatter(formatter)
    records = queue.SimpleQueue()
    queued = QueueHandler(records)
    queued.setFormatter(logging.Formatter('%(message)s'))   # prepare() bakes this into the record: the message only
    logging.basicConfig(level=logging.INFO, handlers=[queued])
    listener = QueueListener(records, *handlers, respect_handler_level=True)
    listener.start()
    return listener


def fast_loop_factory():
    """
    uvloop has no Windows build; winloop (uvloop-compatible) is used when installed, else the default loop.
    Returned as an asyncio.run(loop_factory=...) factory (event loop policies are deprecated since Python 3.14).
    Never combine winloop with tracemalloc: create_server never returns while tracemalloc is tracing (2026-10-05).
    """
    try:
        if sys.platform == 'win32':
            import winloop
            return 'winloop', winloop.new_event_loop
        import uvloop
        return 'uvloop', uvloop.new_event_loop
    except Exception as e:
        errors.report('main.event_loop', e, 'falling back to the default asyncio loop')
        return None, None

FORCE_EXIT_AFTER_SEC = 3.0
LOG_LISTENER = None   # the logging thread (setup_logging), stopped last so the shutdown lines are written


class GracefulExit:
    """
    First Ctrl+C / SIGTERM / SIGBREAK starts a graceful shutdown. Repeats within FORCE_EXIT_AFTER_SEC are ignored
    (key auto-repeat, terminals that deliver Ctrl+C twice); a later repeat forces the exit.
    """
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.shutdown_event = asyncio.Event()
        self._first_signal_at = None

    def __call__(self, signum, frame=None):
        now = time.monotonic()
        if self._first_signal_at is None:
            self._first_signal_at = now
            logger.info(f"Signal {signum} received, initiating graceful shutdown...")
            # Signal handlers installed with signal.signal run outside the loop: hand over thread-safely
            self.loop.call_soon_threadsafe(self.shutdown_event.set)
        elif now - self._first_signal_at >= FORCE_EXIT_AFTER_SEC:
            logger.warning("Force exit!")
            if LOG_LISTENER is not None:
                LOG_LISTENER.stop()   # flushes the queued lines
            logging.shutdown()
            os._exit(1)


class ConsoleQuickEdit:
    """
    Windows console QuickEdit: a mouse click starts a text selection that PAUSES every write to the console, so
    the scanner's event loop blocked on its next log line and the whole bot froze until Enter / Esc.
    Disabled for this console while the bot runs, restored on exit.
    """
    ENABLE_QUICK_EDIT_MODE = 0x0040
    ENABLE_EXTENDED_FLAGS = 0x0080

    def __init__(self):
        self.saved = None
        self.handle = None

    def disable(self):
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            self.handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(self.handle, ctypes.byref(mode)):
                self.saved = mode.value
                kernel32.SetConsoleMode(self.handle, (mode.value & ~self.ENABLE_QUICK_EDIT_MODE) | self.ENABLE_EXTENDED_FLAGS)
        except Exception as e:
            errors.report('main.disable', e, "QuickEdit not changed")

    def restore(self):
        if self.saved is not None:
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleMode(self.handle, self.saved)
            except Exception as e:
                errors.report('main.console_restore', e)
            self.saved = None


def loop_exception_handler(loop: asyncio.AbstractEventLoop, context: dict):
    """
    aiohttp resolves DNS in a shielded task: when the caller already gave up (its timeout), a later DNS failure
    of that task has no awaiter and asyncio logged it as an ERROR with a traceback. The request itself was already
    retried by its caller; a network outage is logged once per event as a WARNING line.
    """
    exc = context.get('exception')
    if isinstance(exc, OSError) and 'shielded future' in (context.get('message') or ''):
        if not NETWORK.failed("DNS resolver", exc):
            logger.warning(f"Network: background DNS resolution failed ({type(exc).__name__} {exc})")
        return
    if isinstance(exc, RuntimeError) and 'UVStream is closing' in str(exc):
        # winloop: TLS data queued for a socket the peer / a reconnect is already closing (2026-10-05 05:12, after a
        # 7.8s loop stall). The connection is gone either way and its owner reconnects: one counted WARNING
        errors.report('winloop.ssl_write_on_closing', exc, context.get('message') or '')
        return
    loop.default_exception_handler(context)


def keep_awake(on: bool) -> None:
    """
    Keep Windows from sleeping while the bot runs (the display may still turn off): on 2026-10-05 the laptop slept
    11:05 -> 12:44 and the bot saw nothing for 1h39m. ES_CONTINUOUS | ES_SYSTEM_REQUIRED, cleared at exit. A closed lid
    or a manual sleep still wins.
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        state = 0x80000000 | (0x00000001 if on else 0)
        if not ctypes.windll.kernel32.SetThreadExecutionState(state):
            raise OSError('SetThreadExecutionState returned 0')
        if on:
            logger.info("Windows sleep blocked while the bot runs")
    except Exception as e:
        errors.report('main.keep_awake', e)


async def main(use_web: bool = True):
    print("Crypto microstructure scanner - loading markets and starting streams (Ctrl+C to stop)")

    quick_edit = ConsoleQuickEdit()
    quick_edit.disable()
    keep_awake(True)
    journal = SignalJournal()
    scanner = Scanner(journal=journal)
    web = None
    if use_web and CONFIG.web.enabled:
        from webui import WebUI
        web = WebUI(scanner)
        try:
            await web.start()
            scanner.web = web
        except OSError as e:
            logger.error(f"Web dashboard could not start on {web.url} ({e}); continuing without it")
            web = None
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(loop_exception_handler)
    graceful_exit = GracefulExit(loop)

    signals = [signal.SIGINT, signal.SIGTERM] + ([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])
    if sys.platform == 'win32':
        # A process started by a shell / tool that ignores Ctrl+C inherits that "ignore" flag (Windows passes
        # SetConsoleCtrlHandler(NULL, TRUE) on to children): Ctrl+C then never reached the bot. Clear it.
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
        except Exception as e:
            errors.report('main.main', e, "Ctrl+C handling not re-enabled")
        # winloop's add_signal_handler did not catch Ctrl+Break (the process died without its shutdown): Python's
        # own handlers cover SIGINT and SIGBREAK on Windows
        for sig in signals:
            signal.signal(sig, graceful_exit)
    else:
        for sig in signals:
            try:
                loop.add_signal_handler(sig, graceful_exit, sig)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, graceful_exit)

    try:
        # Ctrl+C during start-up (e.g. while REST is paused by a rate-limit ban) must not wait for it to finish
        init_task = asyncio.create_task(scanner.initialize())
        stop_task = asyncio.create_task(graceful_exit.shutdown_event.wait())
        await asyncio.wait({init_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        if not init_task.done():
            init_task.cancel()
            await asyncio.gather(init_task, return_exceptions=True)
            logger.info("Shutdown requested during start-up")
            return
        init_task.result()  # re-raise start-up errors
        logger.info("Scanner ready, starting main loop" + (f" - dashboard: {web.url}" if web else ""))
        scanner.start()
        await stop_task
        logger.info("Shutdown signal received, stopping...")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Stopping: closing streams and exchange connections (a few seconds)...")
        if web is not None:
            await web.stop()
        await scanner.stop()
        quick_edit.restore()
        keep_awake(False)
        journal.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto microstructure scanner")
    parser.add_argument("--no-web", action="store_true", help="log only, no browser dashboard")
    args = parser.parse_args()
    # QuickEdit off BEFORE the first console write: a click into the fresh window froze the start at main()'s
    # print (2026-10-04 06:55, the log thread blocked too) - main() disabled it only after that line
    EARLY_QUICK_EDIT = ConsoleQuickEdit()
    EARLY_QUICK_EDIT.disable()
    LOG_LISTENER = setup_logging()
    loop_name, loop_factory = fast_loop_factory()
    logger.info(f"Python {sys.version.split()[0]}, event loop: {loop_name or 'asyncio default'}")
    try:
        asyncio.run(main(use_web=not args.no_web), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal: {e}")
        LOG_LISTENER.stop()
        sys.exit(1)
    LOG_LISTENER.stop()
