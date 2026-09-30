"""
Machine-wide network state: one WARNING when the network goes down, one INFO when it is back.

Measured (2026-09-28..30): the machine lost DNS for ~15h in 8 outages; every stream reconnect, REST poll and
aiohttp's background resolver logged its own WARNING - 13k lines that buried everything else. While the network is
down every further failure of any source is logged at DEBUG; the first data that arrives ends the outage.
"""
import logging
import socket
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _is_network_error(e: BaseException) -> bool:
    if isinstance(e, socket.gaierror) or 'getaddrinfo' in str(e):
        return True
    try:
        import ccxt
        if isinstance(e, ccxt.NetworkError):
            return True
    except ImportError:
        pass
    try:
        import aiohttp
        if isinstance(e, aiohttp.ClientConnectionError):
            return True
    except ImportError:
        pass
    return isinstance(e, (OSError, TimeoutError))


class NetworkState:
    def __init__(self):
        self.down_since: Optional[float] = None
        self.failures = 0

    def failed(self, source: str, e: BaseException) -> bool:
        """
        A request / connection of `source` failed. True when it was handled here (a DNS failure, or any network
        error during an outage): the caller then logs nothing itself.
        """
        dns = isinstance(e, socket.gaierror) or 'getaddrinfo' in str(e)
        if self.down_since is None:
            if not dns:
                return False
            self.down_since, self.failures = time.time(), 1
            logger.warning(f"Network down: {source} cannot resolve hosts ({type(e).__name__} {e}); "
                           f"further failures are logged at DEBUG until data flows again")
            return True
        if not _is_network_error(e):
            return False
        self.failures += 1
        logger.debug(f"Network down: {source} failed ({type(e).__name__} {e})")
        return True

    def ok(self):
        """Data arrived: ends an outage."""
        if self.down_since is not None:
            logger.info(f"Network back after {(time.time() - self.down_since) / 60:.1f} min "
                        f"({self.failures} failed requests / connections)")
            self.down_since, self.failures = None, 0

    @property
    def down(self) -> bool:
        return self.down_since is not None


NETWORK = NetworkState()
