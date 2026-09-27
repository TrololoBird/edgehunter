"""Atomic file writes that survive Windows sharing violations."""
import os
import time

# On Windows a file that was just written is often held open for a moment by the antivirus / search indexer; the
# rename then fails with a sharing violation (WinError 5 / 32) although nothing is wrong. Retrying briefly is the
# documented way to handle it.
REPLACE_ATTEMPTS = 10
REPLACE_WAIT_SEC = 0.05
REPLACE_WAIT_MAX_SEC = 1.0      # waits double up to this: ~6s in total (a 1 MB pickle was held > 1s once)


def atomic_write(path: str, data: bytes):
    """Write `data` to `path` via a temporary file and an atomic rename (readers never see a partial file)."""
    tmp = path + '.tmp'
    with open(tmp, 'wb') as fh:
        fh.write(data)
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(min(REPLACE_WAIT_SEC * 2 ** attempt, REPLACE_WAIT_MAX_SEC))
