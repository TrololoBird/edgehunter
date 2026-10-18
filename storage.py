"""Atomic file replacement with durable writes and Windows sharing retries."""
import os
import tempfile
import time

REPLACE_ATTEMPTS = 10
REPLACE_WAIT_SEC = 0.05
REPLACE_WAIT_MAX_SEC = 1.0


def atomic_write(path: str, data: bytes):
    """Flush a unique sibling tempfile, replace the target, then sync its POSIX directory.

    Concurrent writers publish complete files; the last successful replacement wins.
    A directory-sync failure is reported even though replacement may already have succeeded.
    """
    target = os.path.abspath(os.fspath(path))
    directory = os.path.dirname(target)
    fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(target) + '.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as fh:
            try:
                os.chmod(tmp, os.stat(target).st_mode & 0o777)
            except FileNotFoundError:
                pass
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, target)
                break
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(min(REPLACE_WAIT_SEC * 2 ** attempt, REPLACE_WAIT_MAX_SEC))
        if os.name == 'posix':
            dir_fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
