"""Unit tests for scripts/setup/filelock.py (#374).

Cross-platform advisory lock guarding .env / bundles.state.json read-modify-write
against two concurrent setup.sh invocations. No fcntl/msvcrt: exclusive-create on
the lock file, which is atomic on POSIX and Windows alike.
"""

import threading
import time

import pytest

from scripts.setup import filelock


def test_locked_creates_and_removes_the_lock_file(tmp_path):
    lock_path = tmp_path / ".env.lock"
    with filelock.locked(lock_path):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_locked_releases_on_exception(tmp_path):
    lock_path = tmp_path / ".env.lock"
    with pytest.raises(ValueError):
        with filelock.locked(lock_path):
            raise ValueError("boom")
    assert not lock_path.exists()  # released even though the block raised


def test_second_acquire_blocks_until_first_releases(tmp_path):
    """The core guarantee: a held lock is NOT acquirable -- a second caller must
    wait, not silently proceed and interleave writes."""
    lock_path = tmp_path / ".env.lock"
    assert filelock._try_acquire(lock_path) is True
    assert filelock._try_acquire(lock_path) is False  # already held
    lock_path.unlink()
    assert filelock._try_acquire(lock_path) is True  # free again
    lock_path.unlink()


def test_locked_raises_systemexit_on_timeout(tmp_path):
    lock_path = tmp_path / ".env.lock"
    filelock._try_acquire(lock_path)  # simulate another process holding it
    try:
        with pytest.raises(SystemExit, match="Could not acquire lock"):
            with filelock.locked(lock_path, timeout=0.3):
                pass  # never reached
    finally:
        lock_path.unlink()


def test_stale_lock_is_cleared_and_reacquired(tmp_path, monkeypatch):
    """A lock older than _STALE_SECONDS is treated as abandoned (a crashed
    process), not a real holder -- otherwise one crash would permanently wedge
    every future setup.sh run."""
    monkeypatch.setattr(filelock, "_STALE_SECONDS", 0.2)
    lock_path = tmp_path / ".env.lock"
    filelock._try_acquire(lock_path)  # simulate a crashed holder
    time.sleep(0.3)
    with filelock.locked(lock_path, timeout=2.0):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_locked_is_reentrant_safe_across_sequential_calls(tmp_path):
    """Two sequential (non-overlapping) uses must each succeed cleanly -- the
    common case (no real contention) must not be affected."""
    lock_path = tmp_path / ".env.lock"
    with filelock.locked(lock_path):
        pass
    with filelock.locked(lock_path):
        pass
    assert not lock_path.exists()


def test_two_real_threads_never_overlap_inside_the_critical_section(tmp_path):
    """The actual scenario #374 protects against: two concurrent callers racing
    to read-modify-write the same file. Each thread appends to a shared list
    inside the lock; if the lock ever let both in at once, the interleaved
    append pairs would show up as a lost/duplicated update."""
    lock_path = tmp_path / ".env.lock"
    log = []
    overlap_detected = []

    def worker(name):
        with filelock.locked(lock_path, timeout=5.0):
            if log and log[-1][1] == "start":
                overlap_detected.append(True)
            log.append((name, "start"))
            time.sleep(0.05)  # hold the lock long enough to make a race observable
            log.append((name, "end"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not overlap_detected
    # every start is immediately followed by its own end -- no interleaving
    for i in range(0, len(log), 2):
        assert log[i][1] == "start" and log[i + 1] == (log[i][0], "end")
    assert not lock_path.exists()
