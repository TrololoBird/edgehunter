"""
Historical market data from Binance's public archive (data.binance.vision) for pretraining (pretrain.py):
1m klines of USD-M futures and spot (quote volume + taker buy quote: the same fields as the live streams), the
5-minute `metrics` (open interest, top-trader / global long-short ratios) and funding rates.

Files are cached under CONFIG.pretrain.cache_dir (a second run downloads nothing), downloaded at a capped rate
(the link also carries the live streams: an uncapped download made them lag before, see positioning.py) and
retried on network errors; a 404 is "no data for that period" (not listed yet), not an error.
Liquidations, order books, the other venues, Hyperliquid and Coinbase have no public archive: models learn those
features live only.
"""
import calendar
import csv
import io
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from config import CONFIG

logger = logging.getLogger(__name__)

BASE_URL = 'https://data.binance.vision/data'
MINUTE_MS = 60_000


class RateLimiter:
    """Caps the average download rate (bytes / s) across all requests of the process."""

    def __init__(self, rate: float):
        self.rate = rate
        self.started = time.monotonic()
        self.bytes = 0

    def consumed(self, n: int):
        self.bytes += n
        ahead = self.bytes / self.rate - (time.monotonic() - self.started)
        if ahead > 0:
            time.sleep(ahead)


class Archive:
    def __init__(self, rate_bytes: Optional[float] = None, cache_dir: Optional[str] = None):
        cfg = CONFIG.pretrain
        self.cache_dir = cache_dir or cfg.cache_dir
        self.limiter = RateLimiter(rate_bytes or cfg.download_bytes_per_sec)
        self.downloaded = 0
        self.cached = 0
        self.missing = 0

    # ------------------------------------------------------------------ files

    def _fetch(self, path: str) -> Optional[bytes]:
        """The zip at `path` (cached); None when the archive has no such file."""
        local = os.path.join(self.cache_dir, *path.split('/'))
        if os.path.exists(local):
            with open(local, 'rb') as fh:
                data = fh.read()
            if _is_zip(data):
                self.cached += 1
                return data
            logger.info(f"archive: cached {path} is truncated, downloading it again")
            os.remove(local)
        if os.path.exists(local + '.none'):
            # audit N07: a 404 of a RECENT period may only mean 'not published yet' (the archive lags a day or more):
            # its marker expires after 12h; an old period's 404 is a confirmed absence and stays
            if self._recent(path) and time.time() - os.path.getmtime(local + '.none') > 12 * 3600:
                os.remove(local + '.none')
            else:
                self.missing += 1
                return None
        url = f"{BASE_URL}/{urllib.parse.quote(path)}"          # non-ASCII tickers exist (e.g. Chinese names)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    expected = int(resp.headers.get('Content-Length') or 0)
                    chunks = []
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        self.limiter.consumed(len(chunk))
                    data = b''.join(chunks)
                # a connection cut mid-transfer ends the read early without an error: never cache a partial zip
                if (expected and len(data) != expected) or not _is_zip(data):
                    raise ConnectionError(f"truncated download ({len(data)} of {expected or '?'} bytes)")
                os.makedirs(os.path.dirname(local), exist_ok=True)
                with open(local + '.tmp', 'wb') as fh:
                    fh.write(data)
                os.replace(local + '.tmp', local)
                self.downloaded += len(data)
                return data
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    os.makedirs(os.path.dirname(local), exist_ok=True)
                    open(local + '.none', 'wb').close()
                    self.missing += 1
                    return None
                wait = 2 ** attempt
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                wait = 2 ** attempt
                logger.info(f"archive: {path} failed ({type(e).__name__} {e}), retry in {wait}s")
            time.sleep(wait)
        raise RuntimeError(f"archive: {path} failed 5 times")

    @staticmethod
    def _recent(path: str) -> bool:
        """Does the archive file's period (YYYY-MM-DD / YYYY-MM in its name) end within the last 10 days?"""
        import re
        from datetime import datetime, timezone
        m = re.search(r'(\d{4})-(\d{2})(?:-(\d{2}))?', path.rsplit('/', 1)[-1])
        if not m:
            return True
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        try:
            end = (datetime(y, mo, d, tzinfo=timezone.utc).timestamp() + 86400 if d else
                   datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=timezone.utc).timestamp())
        except ValueError:
            return True
        return time.time() - end < 10 * 86400

    @staticmethod
    def _rows(data: bytes) -> List[List[str]]:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            text = zf.read(zf.namelist()[0]).decode('utf-8')
        rows = list(csv.reader(io.StringIO(text)))
        if rows and rows[0] and not rows[0][0].replace('.', '').replace('-', '').isdigit():
            rows = rows[1:]     # header
        return [r for r in rows if r]

    # ------------------------------------------------------------------ periods

    @staticmethod
    def periods(start: date, end: date) -> Tuple[List[str], List[str]]:
        """Complete months as monthly files ('YYYY-MM'), the rest of the range as daily files ('YYYY-MM-DD')."""
        months, days = [], []
        d = start
        while d <= end:
            month_end = (date(d.year + (d.month == 12), d.month % 12 + 1, 1) - timedelta(days=1))
            if d.day == 1 and month_end <= end:
                months.append(f"{d.year:04d}-{d.month:02d}")
                d = month_end + timedelta(days=1)
            else:
                days.append(d.isoformat())
                d += timedelta(days=1)
        return months, days

    # ------------------------------------------------------------------ datasets

    def klines_1m(self, market: str, symbol: str, start: date, end: date) -> np.ndarray:
        """
        1m klines as float64 [open_time_ms, open, high, low, close, volume, quote_volume, taker_buy_quote], sorted,
        de-duplicated. `market`: 'futures' (USD-M) or 'spot'.
        """
        root = 'futures/um' if market == 'futures' else 'spot'
        months, days = self.periods(start, end)
        paths = [f"{root}/monthly/klines/{symbol}/1m/{symbol}-1m-{m}.zip" for m in months]
        paths += [f"{root}/daily/klines/{symbol}/1m/{symbol}-1m-{d}.zip" for d in days]
        out = []
        for path in paths:
            data = self._fetch(path)
            if data is None:
                continue
            for r in self._rows(data):
                ts = float(r[0])
                if ts > 1e14:       # spot switched to microseconds in 2025
                    ts /= 1000.0
                out.append((ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[7]),
                            float(r[10])))
        if not out:
            return np.empty((0, 8))
        arr = np.asarray(out, dtype=np.float64)
        arr = arr[np.argsort(arr[:, 0], kind='stable')]
        keep = np.concatenate(([True], np.diff(arr[:, 0]) > 0))
        return arr[keep]

    def metrics(self, symbol: str, start: date, end: date) -> Dict[str, np.ndarray]:
        """
        5-minute metrics: 'ts' (snapshot time ms), 'oi' (open interest, base units), 'oi_usd', 'top_pos' (top
        traders' long/short position ratio), 'top_acc' (top accounts), 'global' (all accounts).
        """
        rows = []
        d = start
        while d <= end:
            data = self._fetch(f"futures/um/daily/metrics/{symbol}/{symbol}-metrics-{d.isoformat()}.zip")
            if data is not None:
                for r in self._rows(data):
                    try:
                        rows.append((_utc_ms(r[0]), float(r[2] or 0), float(r[3] or 0), float(r[5] or 0),
                                     float(r[4] or 0), float(r[6] or 0)))
                    except (ValueError, IndexError):
                        continue
            d += timedelta(days=1)
        if not rows:
            return {k: np.empty(0) for k in ('ts', 'oi', 'oi_usd', 'top_pos', 'top_acc', 'global')}
        arr = np.asarray(sorted(set(rows)), dtype=np.float64)
        return {'ts': arr[:, 0], 'oi': arr[:, 1], 'oi_usd': arr[:, 2], 'top_pos': arr[:, 3], 'top_acc': arr[:, 4],
                'global': arr[:, 5]}

    def funding(self, symbol: str, start: date, end: date, raw: bool = False) -> np.ndarray:
        """Funding settlements [calc_time_ms, rate normalized to 8h (raw=True: the rate paid at that settlement)]."""
        months, days = self.periods(start, end)
        months += sorted({d[:7] for d in days})
        out = []
        for m in months:
            data = self._fetch(f"futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{m}.zip")
            if data is None:
                continue
            for r in self._rows(data):
                try:
                    rate = float(r[2])
                    out.append((float(r[0]), rate if raw else rate * 8 / max(1.0, float(r[1] or 8))))
                except (ValueError, IndexError):
                    continue
        if not out:
            return np.empty((0, 2))
        arr = np.asarray(sorted(set(out)), dtype=np.float64)
        return arr


    def klines_1d(self, market: str, symbol: str, start: date, end: date) -> np.ndarray:
        """
        Daily klines [open_time_ms, close, quote_volume] of the COMPLETE months in [start, end] (monthly files only:
        the running month has only daily files, and a daily 1d file per coin and day is thousands of requests).
        """
        root = 'futures/um' if market == 'futures' else 'spot'
        months, _ = self.periods(date(start.year, start.month, 1), end)
        out = []
        for m in months:
            data = self._fetch(f"{root}/monthly/klines/{symbol}/1d/{symbol}-1d-{m}.zip")
            if data is None:
                continue
            for r in self._rows(data):
                ts = float(r[0])
                if ts > 1e14:
                    ts /= 1000.0
                out.append((ts, float(r[4]), float(r[7])))
        if not out:
            return np.empty((0, 3))
        arr = np.asarray(sorted(set(out)), dtype=np.float64)
        return arr

    def klines_ohlc(self, market: str, symbol: str, interval: str, start: date, end: date) -> np.ndarray:
        """
        Klines [open_time_ms, open, high, low, close, quote_volume] of `interval` (e.g. '1h') over the COMPLETE months
        in [start, end] (monthly files only, like `klines_1d`).
        """
        root = 'futures/um' if market == 'futures' else 'spot'
        months, _ = self.periods(date(start.year, start.month, 1), end)
        out = []
        for m in months:
            data = self._fetch(f"{root}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{m}.zip")
            if data is None:
                continue
            for r in self._rows(data):
                ts = float(r[0])
                if ts > 1e14:
                    ts /= 1000.0
                out.append((ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7])))
        if not out:
            return np.empty((0, 6))
        return np.asarray(sorted(set(out)), dtype=np.float64)

    def list_symbols(self, market: str) -> List[str]:
        """
        Every symbol the archive has monthly klines for, INCLUDING delisted ones (the S3 listing of data.binance.vision,
        paginated; cached for a day): pretraining picks its coins from the past, not from today's exchange.
        """
        import json
        import re
        root = 'futures/um' if market == 'futures' else 'spot'
        cache = os.path.join(self.cache_dir, f"symbols_{market.replace('/', '_')}.json")
        if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 86_400:
            with open(cache) as fh:
                return json.load(fh)
        prefix = f"data/{root}/monthly/klines/"
        symbols: List[str] = []
        marker = ''
        while True:
            url = (f"https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix={prefix}"
                   + (f"&marker={urllib.parse.quote(marker)}" if marker else ''))
            for attempt in range(5):
                try:
                    with urllib.request.urlopen(url, timeout=60) as resp:
                        text = resp.read().decode('utf-8')
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                    logger.info(f"archive: listing failed ({type(e).__name__} {e}), retry")
                    time.sleep(2 ** attempt)
            else:
                raise RuntimeError('archive: symbol listing failed 5 times')
            symbols += [p[len(prefix):].rstrip('/') for p in re.findall(r'<Prefix>([^<]+)</Prefix>', text)
                        if p != prefix]
            nxt = re.search(r'<NextMarker>([^<]+)</NextMarker>', text)
            if '<IsTruncated>true</IsTruncated>' not in text or not nxt:
                break
            marker = nxt.group(1)
        symbols = sorted(set(symbols))
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(cache, 'w') as fh:
            json.dump(symbols, fh)
        return symbols


def _is_zip(data: bytes) -> bool:
    """A complete zip archive (its central directory at the end is intact)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return bool(zf.namelist())
    except zipfile.BadZipFile:
        return False


def _utc_ms(text: str) -> float:
    """'2026-09-25 01:30:00' (UTC) -> epoch ms."""
    return calendar.timegm(time.strptime(text, '%Y-%m-%d %H:%M:%S')) * 1000.0
