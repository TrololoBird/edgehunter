"""Optional append-only raw event journal for independent validation.

The logger is disabled unless ``EDGEHUNTER_RAW_LOG_DIR`` is set. It stores one
gzip JSONL member per event, preserving the bytes received before parsing and
the local receive clocks. It deliberately has no dependency on the scanner's
signal or replay code.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import threading
import time
import uuid
from queue import Queue, Full
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class RawEventLog:
    def __init__(self, root: Optional[str] = None, parser_version: str = 'raw-v1'):
        configured = root or os.environ.get('EDGEHUNTER_RAW_LOG_DIR')
        self.root = Path(configured) if configured else None
        self.parser_version = parser_version
        self._lock = threading.Lock()
        self._queue = Queue(maxsize=20_000)
        self._writer_started = False

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def append(self, *, source: str, venue: str, channel: str, connection_id: str,
               payload: bytes, exchange_event_time: Any = None,
               sequence_start: Any = None, sequence_end: Any = None,
               symbol: Optional[str] = None, metadata: Optional[dict[str, Any]] = None) -> Optional[str]:
        if not self.enabled:
            return None
        now_wall = time.time_ns()
        event_id = uuid.uuid4().hex
        digest = hashlib.sha256(payload).hexdigest()
        day = datetime.fromtimestamp(now_wall / 1e9, timezone.utc).strftime('%Y-%m-%d')
        assert self.root is not None
        safe_channel = ''.join(c if c.isalnum() or c in '._-' else '_' for c in (channel or 'unknown'))[:180]
        path = self.root / source / venue / day / f'{safe_channel}.jsonl.gz'
        record = {
            'event_id': event_id, 'source': source, 'venue': venue,
            'channel': channel, 'symbol': symbol, 'connection_id': connection_id,
            'recv_monotonic_ns': time.monotonic_ns(), 'recv_wall_time_ns': now_wall,
            'exchange_event_time': exchange_event_time,
            'sequence_start': sequence_start, 'sequence_end': sequence_end,
            'payload_sha256': digest,
            'raw_payload_b64': base64.b64encode(payload).decode('ascii'),
            'parser_version': self.parser_version,
            'metadata': metadata or {},
        }
        line = (json.dumps(record, separators=(',', ':'), ensure_ascii=False) + '\n').encode()
        self._start_writer()
        try:
            self._queue.put_nowait((path, line))
        except Full:
            # Evidence capture must never stall market ingestion. Dropped raw records
            # are visible through the queue capacity and do not affect parsed signals.
            pass
        return event_id

    def _start_writer(self) -> None:
        if self._writer_started:
            return
        with self._lock:
            if self._writer_started:
                return
            self._writer_started = True
            threading.Thread(target=self._writer, name='raw-event-writer', daemon=True).start()

    def flush(self) -> None:
        """Wait for queued records (offline readers / orderly shutdown; never on the event loop)."""
        self._queue.join()

    def _writer(self) -> None:
        while True:
            path, line = self._queue.get()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(path, 'ab') as fh:
                    fh.write(line)
            except OSError:
                pass
            finally:
                self._queue.task_done()

    def append_rest(self, *, venue: str, endpoint: str, params_hash: str,
                    sent_wall_time_ns: int, response_wall_time_ns: int,
                    status: Optional[int], payload: bytes = b'', error: Optional[str] = None,
                    rate_limit_headers: Optional[dict[str, str]] = None) -> Optional[str]:
        """Record a REST response using the same append-only envelope."""
        return self.append(source='rest', venue=venue, channel=endpoint,
                           connection_id=params_hash, payload=payload,
                           exchange_event_time=None,
                           sequence_start=None, sequence_end=None,
                           metadata={'status': status, 'error': error,
                                     'params_hash': params_hash,
                                     'sent_wall_time_ns': sent_wall_time_ns,
                                     'response_wall_time_ns': response_wall_time_ns,
                                     'rate_limit_headers': rate_limit_headers or {}})
