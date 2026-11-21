#!/usr/bin/env python3
"""EdgeHunter v2 runtime boundary.

The working process may collect and display timestamped market observations,
but it has no admitted strategy until ``core.source_manifest`` contains a
reviewed primary-source contract.  Legacy strategy names, historical rows,
models and replay results are forensic artifacts and are not loaded into the
v2 signal or execution path.  The executor is disabled by default and this
entry point never treats a reference or replay price as an exchange fill.
"""

import os
# polars' bundled mimalloc kept freed memory committed: 579 MB of large private blocks against ~290 MB of live
# structures (memreport, 2026-10-05). Purge freed pages at once; set before polars loads (the workers inherit it).
os.environ.setdefault('MIMALLOC_PURGE_DELAY', '0')
# On Linux polars ships jemalloc, not mimalloc (the line above only applies to Windows): the VPS held ~1.9 GB of large
# private blocks against ~0.7 GB of live structures (Memory line, 2026-10-27). Decay freed pages after 2 s and let a
# background thread do it (without one jemalloc purges only when the process allocates again).
os.environ.setdefault('_RJEM_MALLOC_CONF', 'background_thread:true,dirty_decay_ms:2000,muzzy_decay_ms:2000')

import argparse
import asyncio
import logging
import errors
import os
import signal
import sys
import time
import queue
import re
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from dataclasses import replace

from config import CONFIG
from journal import SignalJournal
from netstate import NETWORK
from scanner import Scanner

logger = logging.getLogger(__name__)

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:BINGX_API_KEY|BINGX_API_SECRET|TELEGRAM_BOT_TOKEN|API[_-]?KEY|API[_-]?SECRET|"
    r"ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|BOT[_-]?TOKEN|TOKEN|SECRET|KEY|PASSWORD|PRIVATE[_-]?KEY)\b\s*[=:]\s*)"
    r"([^\s,;&]+)"
)
_URL_SECRET = re.compile(r"(?i)([?&](?:api[_-]?key|key|signature|token|secret|access[_-]?token)=)[^&\s]+")
_TELEGRAM_CREDENTIAL = re.compile(r"(?i)(/bot)\d{6,}:[A-Za-z0-9_-]{20,}")


def redact_secrets(message: str) -> str:
    """Redact common credential assignments and Telegram bot tokens in log text."""
    message = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", str(message))
    message = _URL_SECRET.sub(r"\1[REDACTED]", message)
    return _TELEGRAM_CREDENTIAL.sub(r"\1[REDACTED]", message)


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_secrets(record.getMessage())
            record.args = ()
        except (TypeError, ValueError):
            record.msg = "[unrenderable log message redacted]"
            record.args = ()
        return True


def apply_data_only_mode() -> bool:
    """Disable order, strategy and outbound-message paths for an analytics collection run."""
    if os.environ.get('EDGEHUNTER_DATA_ONLY', '').strip().lower() not in {'1', 'true', 'yes'}:
        return False
    object.__setattr__(CONFIG, 'executor', replace(CONFIG.executor, enabled=False))
    object.__setattr__(CONFIG, 'strategies', replace(CONFIG.strategies, enabled=()))
    object.__setattr__(CONFIG, 'notify', replace(CONFIG.notify, enabled=False, toast=False))
    object.__setattr__(CONFIG, 'briefing', replace(CONFIG.briefing, enabled=False))
    logger.info('Data-only mode active: executor, strategy admission, and outbound notifications disabled')
    return True


def setup_logging() -> QueueListener:
    """
    Console + a size-rotated scanner.log (a long run never grows the file without bound), written by a listener
    THREAD: the loop only queues records. A console write blocks while the window has a selection or conhost is
    paged out (measured: the loop stalled 2s inside StreamHandler.emit).
    """
    cfg = CONFIG.logging
    level_name = os.environ.get('EDGEHUNTER_LOG_LEVEL', 'INFO').strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"invalid EDGEHUNTER_LOG_LEVEL: {level_name!r}")
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s', datefmt='%H:%M:%S')
    handlers = [logging.StreamHandler(sys.stdout),
                RotatingFileHandler(cfg.file, maxBytes=cfg.max_bytes, backupCount=cfg.backups, encoding='utf-8')]
    for handler in handlers:
        handler.setFormatter(formatter)
    records = queue.SimpleQueue()
    queued = QueueHandler(records)
    queued.setFormatter(logging.Formatter('%(message)s'))   # prepare() bakes this into the record: the message only
    queued.addFilter(SecretRedactionFilter())
    logging.basicConfig(level=level, handlers=[queued])
    # DEBUG is for Edgehunter's data path. Keep dependency protocol chatter
    # bounded and prevent libraries from logging complete request URLs.
    for name in ('aiohttp', 'asyncio', 'ccxt', 'websockets', 'urllib3'):
        logging.getLogger(name).setLevel(logging.WARNING)
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
SHUTDOWN_DEADLINE_SEC = 75.0  # keep a margin below systemd TimeoutStopSec=90s
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


_BYTESIO_GC = {'n': 0, 'logged_at': 0.0}


def unraisable_hook(unraisable) -> None:
    """
    'Exception ignored while finalizing file <_io.BytesIO>: BufferError: Existing exports of data' (~10-40 a day, a
    5-line traceback at a random line - wherever the gc happened to run): a BytesIO collected in one reference cycle
    with a memoryview of its buffer (multiprocessing pickles to BytesIO.getbuffer()); the gc finalizes the BytesIO
    first and its close() refuses while the view exists. Both were garbage already - nothing is lost. Python 3.13+
    reports it (IOBase's finalizer stopped swallowing close() errors; RhysU/jobserver#444). One INFO line an hour
    with the count; everything else goes to Python's own hook.
    """
    # the finalizer reports with object None and the BytesIO's repr in err_msg
    if isinstance(unraisable.exc_value, BufferError) and \
            (unraisable.err_msg or '').startswith('Exception ignored while finalizing file <_io.BytesIO'):
        _BYTESIO_GC['n'] += 1
        now = time.time()
        if now - _BYTESIO_GC['logged_at'] >= 3600:
            logger.info(f"gc: {_BYTESIO_GC['n']} BytesIO finalized beside a live memoryview (harmless BufferError)")
            _BYTESIO_GC.update(n=0, logged_at=now)
        return
    sys.__unraisablehook__(unraisable)


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
    apply_data_only_mode()
    print("EdgeHunter - loading markets and starting streams (Ctrl+C to stop)")
    # the streams allocate millions of short-lived tuples a minute: the default gen-0 threshold (2000) promoted them
    # into gen 2 and its full collections paused the loop 0.3s+ (watchdog 'gc (gen 2)', 100+ a day); fewer, younger
    # collections - long-lived history is kept in compact arrays; the fetcher no
    # longer calls gc.freeze(), so this comment must not imply frozen ownership.
    import gc
    gc.set_threshold(*(int(x) for x in (os.environ.get('EDGEHUNTER_GC_THRESHOLD') or os.environ.get('PUMP_GC_THRESHOLD', '50000,20,100')).split(',')))

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
        async def close_components():
            if web is not None:
                await web.stop()
            await scanner.stop()

        try:
            await asyncio.wait_for(close_components(), timeout=SHUTDOWN_DEADLINE_SEC)
        except asyncio.TimeoutError:
            # systemd will terminate the service shortly after TimeoutStopSec;
            # keep the deadline explicit so a stuck cleanup cannot hide why it
            # was interrupted.
            logger.error(f"Shutdown cleanup exceeded {SHUTDOWN_DEADLINE_SEC:.0f}s deadline")
        quick_edit.restore()
        keep_awake(False)
        journal.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EdgeHunter crypto market analysis and signals")
    parser.add_argument("--no-web", action="store_true", help="log only, no browser dashboard")
    args = parser.parse_args()
    # QuickEdit off BEFORE the first console write: a click into the fresh window froze the start at main()'s
    # print (2026-10-04 06:55, the log thread blocked too) - main() disabled it only after that line
    EARLY_QUICK_EDIT = ConsoleQuickEdit()
    EARLY_QUICK_EDIT.disable()
    LOG_LISTENER = setup_logging()
    sys.unraisablehook = unraisable_hook
    # uvloop 0.22.1 binds asyncio.iscoroutinefunction (deprecated in 3.14) and calls it in add_signal_handler and
    # run_in_executor, so the warning names OUR call site (main.py:224). Fixed in uvloop 0.23.0, but ccxt (4.5.90)
    # pins uvloop==0.22.1: silenced by its exact text until ccxt lets uvloop move
    import warnings
    warnings.filterwarnings('ignore', message=r"'asyncio\.iscoroutinefunction' is deprecated", category=DeprecationWarning)
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
