"""Point-in-time macro context.

The public FRED CSV is a current, revised series. It is not a historical
vintage and therefore cannot be used to reconstruct what a trading process
knew at an old timestamp. v2 accepts only rows carrying an explicit release
timestamp (for example an ALFRED vintage or a release-event archive). A
current FRED download can still be cached for inspection, but it produces no
decision features in strict mode.
"""
import errors
import csv
import io
import json
import os
import time
from security import safe_urlopen
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple
from storage import atomic_write
from config import CONFIG

SERIES = {'us10y': 'DGS10', 'dxy': 'DTWEXBGS', 'brent': 'DCOILBRENTEU'}
URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
CACHE = os.path.join('models', 'macro_cache.json')
DAY_MS = 86_400_000


def available_ms(name: str, obs_day_ms: float) -> float:
    """audit N06: when an observation dated obs_day_ms (UTC day start) is public, conservatively."""
    wd = int(obs_day_ms // DAY_MS + 3) % 7               # 0 = Monday (1970-01-01 was a Thursday)
    if name == 'dxy':
        # H.10: weekly, the Monday after the observation's week, 16:15 ET (~21:15 UTC; 22:00 taken)
        return obs_day_ms + (7 - wd) * DAY_MS + 22 * 3_600_000
    if name == 'brent':
        return obs_day_ms + 8 * DAY_MS                    # EIA spot prices: weekly release, up to ~a week late
    # DGS10 (H.15): the next business day ~16:15 ET; a Friday's value on Monday
    return obs_day_ms + (3 if wd == 4 else 2 if wd == 5 else 1) * DAY_MS + 22 * 3_600_000


MACRO_FEATURES = ('us10y_5d_bp', 'dxy_5d', 'brent_5d')


def fetch(series_id: str, timeout: Optional[float] = None) -> List[Tuple[int, float]]:
    """[(day start ms, value)] of a FRED series; '.' (holidays) skipped."""
    with safe_urlopen(URL.format(series_id), timeout=timeout or CONFIG.rest.total_timeout_sec) as resp:
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
    def __init__(self, data: Optional[Dict[str, List[Tuple[int, float]]]] = None, *, strict_pit: bool = True):
        self.data = data or {}
        self.strict_pit = bool(strict_pit)
        self.loaded_at = 0.0
        self._pit_rows: Dict[str, List[Tuple[int, float, int]]] = {}

    def refresh(self, max_age_sec: float = 6 * 3600) -> bool:
        """Download (or read the cache when it is fresh); True when every series is present."""
        try:
            if os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < max_age_sec:
                with open(CACHE, encoding='utf-8') as fh:
                    self.data = {k: [tuple(x) for x in v] for k, v in json.load(fh).items()}
            else:
                self.data = {name: fetch(sid) for name, sid in SERIES.items()}
                os.makedirs(os.path.dirname(CACHE), exist_ok=True)
                atomic_write(CACHE, json.dumps(self.data).encode('utf-8'))
            self.loaded_at = time.time()
            self._pit_rows = {}
        except Exception as e:
            errors.report('macro.refresh', e)
            return False
        if self.strict_pit and not all(self.data.get(k) and all(len(row) >= 3 for row in self.data[k]) for k in SERIES):
            # The current FRED CSV is useful for a human dashboard, but it is
            # not a release-time dataset and must not be advertised as a
            # usable historical provider.
            return False
        return all(self.data.get(k) for k in SERIES)

    def _asof(self, name: str, ts_ms: float, back: int = 0) -> Optional[float]:
        """Return the latest observation known at ``ts_ms``.

        A PIT table may contain several vintages of one observation.  First
        choose the latest vintage released by the decision time for each
        observation date, then move ``back`` observations in observation-time
        order.  Sorting by release time alone would return an older observation
        from a later revision and would make a five-observation change depend
        on the number of revisions in the file.
        """
        if name not in self._pit_rows:
            rows = self.data.get(name) or []
            parsed: List[Tuple[int, float, int]] = []
            for r in rows:
                try:
                    obs, value = int(r[0]), float(r[1])
                    if len(r) >= 3:
                        release = int(r[2])
                    elif self.strict_pit:
                        # Unknown release time is never usable in strict PIT
                        # mode; keeping it at +inf makes that explicit.
                        release = 2**63 - 1
                    else:
                        release = int(available_ms(name, obs))
                except (TypeError, ValueError, IndexError):
                    continue
                parsed.append((obs, value, release))
            self._pit_rows[name] = parsed
        latest: Dict[int, Tuple[float, int]] = {}
        for obs, value, release in self._pit_rows[name]:
            if release <= ts_ms and (obs not in latest or release >= latest[obs][1]):
                latest[obs] = (value, release)
        observations = sorted(latest.items())
        i = len(observations) - 1 - int(back)
        return observations[i][1][0] if 0 <= i < len(observations) else None

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
