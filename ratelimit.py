"""
Proactive REST rate limiting.

Every REST call goes through a RestGate. A gate does two things:
- it stays under a weight budget instead of waiting for a ban: after each call it reads the exchange's own counter
  (Binance `X-MBX-USED-WEIGHT-1M`, Bybit `X-Bapi-Limit-Status`), keeps a local estimate in between, and makes
  callers wait for the next minute when the budget for their priority is used up (priority 0 may use the whole
  budget, lower priorities a smaller share, so candle backfills never queue behind journal evaluation);
- on a 429 / 418 / 403 it pauses every caller of the gate (and of gates sharing its BanState) until the ban ends,
  parsed from `banned until <ms>` or `Retry-After`, with exponential backoff as a fallback.
"""
import asyncio
import logging
import re
import time
from typing import Any, Dict, Optional

from ccxt import DDoSProtection, RateLimitExceeded

from config import CONFIG

logger = logging.getLogger(__name__)

# ccxt maps HTTP 429 / Binance -1003 to RateLimitExceeded and HTTP 418 (IP ban) / 403 to DDoSProtection
RATE_LIMIT_ERRORS = (RateLimitExceeded, DDoSProtection)
# 418 bodies carry the ban end as a ms timestamp: "... IP(1.2.3.4) banned until 1790358356564 ..."
_BAN_UNTIL_RE = re.compile(r'banned until (\d{12,})')


class BanState:
    """Shared pause: one ban (per IP / API cluster) stops every gate that shares this object."""

    def __init__(self):
        self.resume_at = 0.0
        self.backoff = 1.0

    async def wait(self):
        while (delay := self.resume_at - time.time()) > 0:
            await asyncio.sleep(delay)

    def pause(self, seconds: float, reason: str, name: str):
        resume_at = time.time() + seconds
        if resume_at > self.resume_at:
            self.resume_at = resume_at
            logger.warning(f"REST {name} rate limited, pausing for {seconds:.0f}s: {reason[:200]}")


def _header(headers: Dict[str, str], name: str) -> Optional[str]:
    name = name.lower()
    return next((v for k, v in (headers or {}).items() if k.lower() == name), None)


class RestGate:
    def __init__(self, name: str, weight_limit_per_min: int, ban: Optional[BanState] = None,
                 used_weight_header: Optional[str] = None):
        self.name = name
        self.limit = weight_limit_per_min
        self.ban = ban or BanState()
        self.used_weight_header = used_weight_header
        self._minute = 0
        self._used = 0.0
        self.calls = 0

    # ------------------------------------------------------------------ budget

    def _roll(self, now: float):
        minute = int(now // 60)
        if minute != self._minute:
            self._minute, self._used = minute, 0.0

    def budget(self, priority: int) -> float:
        cfg = CONFIG.rest
        shares = cfg.priority_shares
        share = shares[min(max(priority, 0), len(shares) - 1)]
        return self.limit * cfg.budget_share * share

    @property
    def used(self) -> float:
        self._roll(time.time())
        return self._used

    async def _wait_budget(self, weight: float, priority: int):
        while True:
            await self.ban.wait()
            now = time.time()
            self._roll(now)
            if self._used + weight <= self.budget(priority):
                self._used += weight
                return
            # Weight windows are per calendar minute (Binance resets at :00): wait for the next one
            await asyncio.sleep(60 - now % 60 + 0.05)

    def _sync_from_headers(self, exchange):
        headers = getattr(exchange, 'last_response_headers', None) or {}
        if self.used_weight_header:
            value = _header(headers, self.used_weight_header)
            if value is not None:
                try:
                    self._used = max(self._used, float(value))
                except ValueError:
                    pass
        # Bybit: "X-Bapi-Limit-Status" = remaining requests in the current window for this endpoint
        remaining = _header(headers, 'X-Bapi-Limit-Status')
        limit = _header(headers, 'X-Bapi-Limit')
        if remaining is not None and limit:
            try:
                self._used = max(self._used, self.limit * (1 - float(remaining) / float(limit)))
            except (ValueError, ZeroDivisionError):
                pass

    # ------------------------------------------------------------------ ban handling

    def _ban_seconds(self, exc: Exception, exchange) -> float:
        match = _BAN_UNTIL_RE.search(str(exc))
        if match:
            return max(1.0, int(match.group(1)) / 1000 - time.time() + 1.0)
        retry_after = _header(getattr(exchange, 'last_response_headers', None) or {}, 'Retry-After')
        if retry_after:
            try:
                return max(1.0, float(retry_after))
            except (TypeError, ValueError):
                pass
        wait = self.ban.backoff
        self.ban.backoff = min(self.ban.backoff * 2, 60.0)
        return wait

    # ------------------------------------------------------------------ call

    async def call(self, exchange, method: str, *args, weight: float = 1, priority: int = 1, **kwargs) -> Any:
        """Run `exchange.<method>(*args, **kwargs)` within the budget; on 429/418 pause everyone and retry."""
        attempts = CONFIG.rest.max_retries
        for attempt in range(1, attempts + 1):
            await self._wait_budget(weight, priority)
            try:
                result = await getattr(exchange, method)(*args, **kwargs)
                self.calls += 1
                self.ban.backoff = 1.0
                self._sync_from_headers(exchange)
                return result
            except RATE_LIMIT_ERRORS as e:
                self.ban.pause(self._ban_seconds(e, exchange), str(e), self.name)
                if attempt == attempts:
                    raise
