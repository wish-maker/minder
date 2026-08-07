"""Cross-platform advisory file lock (#374).

fill_env_secrets()/`bundle`'s _set_enabled()/seed_profile() each read-modify-write
.env / bundles.state.json with no lock -- two concurrent setup.sh invocations (e.g.
`install` racing a cron-driven `status --fix`, or two terminals) can interleave
writes and corrupt either file. Uses an exclusive-create lock FILE (not fcntl.flock,
which doesn't exist on Windows -- this module also runs via `python -m scripts.setup`
on hantal) so it works identically on POSIX and Windows with stdlib only.

Advisory only: a process that crashes while holding the lock leaves it behind.
Guarded by a staleness check (_STALE_SECONDS) rather than requiring manual cleanup --
matches this being a rare-edge-case mitigation, not a hard guarantee (#374's own
framing: "a design choice bigger than a quick fix" was rejected in favor of exactly
this simple, timeout-bounded approach).
"""

import os
import time
from contextlib import contextmanager
from pathlib import Path

_POLL_SECONDS = 0.2
_STALE_SECONDS = 300  # abandon a lock this old -- a real setup.sh run never takes 5 min


def _try_acquire(lock_path: Path) -> bool:
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.close(fd)
    return True


def _clear_if_stale(lock_path: Path) -> None:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return  # already gone -- another waiter cleared it, or it never existed
    if age > _STALE_SECONDS:
        try:
            lock_path.unlink()
        except OSError:
            pass  # lost the race to remove it -- fine, _try_acquire will just fail again


@contextmanager
def locked(lock_path: Path, *, timeout: float = 10.0):
    """Hold an exclusive advisory lock at ``lock_path`` for the block's duration.

    Raises SystemExit with a clear message if another process holds it past
    ``timeout`` seconds -- callers should NOT catch this; a caller mid-write is
    exactly the case this exists to protect.
    """
    deadline = time.monotonic() + timeout
    while not _try_acquire(lock_path):
        _clear_if_stale(lock_path)
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"Could not acquire lock {lock_path} within {timeout}s -- "
                "another setup.sh is already running. Wait for it to finish, or "
                f"remove {lock_path} if you're sure nothing is actually running."
            )
        time.sleep(_POLL_SECONDS)
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass
