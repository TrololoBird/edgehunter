"""
Macro context from FRED (St. Louis Fed; public CSV, no key): US 10-year Treasury yield (DGS10), the broad trade-
weighted dollar index (DTWEXBGS) and Brent crude (DCOILBRENTEU). Daily values published with a delay of about a
day, so a value is used only from the day AFTER its date (no look-ahead in training, the same rule live).

Features: the 5-trading-day change of each series as of the previous day (yield in basis points, dollar and Brent in
%). Context for the scenario card and a candidate input of its probability model (`train_scenarios.py --macro`);
not a signal by itself.
"""
import bisect
import csv
import io
import json
import os
import time
import urllib.request
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

SERIES = {'us10y': 'DGS10', 'dxy': 'DTWEXBGS', 'brent': 'DCOILBRENTEU'}
URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
CACHE = os.path.join('models', 'macro_cache.json')
DAY_MS = 86_400_000
MACRO_FEATURES = ('us10y_5d_bp', 'dxy_5d', 'brent_5d')


def fetch(series_id: str, timeout: float = 20) -> List[Tuple[int, float]]:
    """[(day start ms, value)] of a FRED series; '.' (holidays) skipped."""
    with urllib.request.urlopen(URL.format(series_id), timeout=timeout) as resp:
        text = resp.read().decode('utf-8')
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or not row[0][:1].isdigit():
            continue
        try:
            d = date.fromisoformat(row[0])
            out.append((int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000), float(row[1])))
        except ValueError:
            continue
    return out


class Macro:
    def __init__(self, data: Optional[Dict[str, List[Tuple[int, float]]]] = None):
        self.data = data or {}
        self.loaded_at = 0.0
        self._ts: Dict[str, List[int]] = {}

    def refresh(self, max_age_sec: float = 6 * 3600) -> bool:
        """Download (or read the cache when it is fresh); True when every series is present."""
        try:
            if os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < max_age_sec:
                with open(CACHE, encoding='utf-8') as fh:
                    self.data = {k: [tuple(x) for x in v] for k, v in json.load(fh).items()}
            else:
                self.data = {name: fetch(sid) for name, sid in SERIES.items()}
                os.makedirs(os.path.dirname(CACHE), exist_ok=True)
                with open(CACHE, 'w', encoding='utf-8') as fh:
                    json.dump(self.data, fh)
            self.loaded_at = time.time()
            self._ts = {}
        except Exception:
            return False
        return all(self.data.get(k) for k in SERIES)

    def _asof(self, name: str, ts_ms: float, back: int = 0) -> Optional[float]:
        rows = self.data.get(name) or []
        if name not in self._ts:
            self._ts[name] = [r[0] for r in rows]
        # a daily value is known from the next day on
        i = bisect.bisect_right(self._ts[name], ts_ms - DAY_MS) - 1 - back
        return rows[i][1] if 0 <= i < len(rows) else None

    def features(self, ts_ms: float) -> Dict[str, float]:
        out = {}
        for name, key, scale, pct in (('us10y', 'us10y_5d_bp', 100.0, False), ('dxy', 'dxy_5d', 100.0, True),
                                      ('brent', 'brent_5d', 100.0, True)):
            now, before = self._asof(name, ts_ms), self._asof(name, ts_ms, 5)
            if now is None or before is None:
                out[key] = float('nan')
            else:
                out[key] = (now / before - 1) * scale if pct else (now - before) * scale
        return out

    def snapshot(self, ts_ms: float) -> Dict[str, Optional[float]]:
        """Last known levels + 5-day changes (for the dashboard)."""
        f = self.features(ts_ms)
        return {'us10y': self._asof('us10y', ts_ms), 'dxy': self._asof('dxy', ts_ms),
                'brent': self._asof('brent', ts_ms), **f}
