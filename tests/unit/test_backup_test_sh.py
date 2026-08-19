"""Unit tests for scripts/backup-test.sh (#430).

The quick backup verifier must PASS only when the latest artifact of each kind
(postgres/redis/neo4j/snapshot) exists, is recent, is non-empty, and is a valid
archive — and FAIL loudly otherwise (missing / stale / truncated / corrupt), so
the Pi's `20 2 * * * backup-test.sh --quick` cron does real work instead of the
silent `not found` no-op it was before. Runs the real script via bash against a
temp backups dir.
"""

import gzip
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup-test.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None
    or shutil.which("gzip") is None
    or shutil.which("tar") is None,
    reason="needs bash + gzip + tar",
)


def _write_gz(path: Path, payload: bytes | None = None) -> None:
    # incompressible payload so the gz stays comfortably above the min-bytes floor
    payload = payload if payload is not None else os.urandom(4000)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as f:
        f.write(payload)


def _write_targz(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("member.bin")
        data = os.urandom(4000)
        info.size = len(data)
        import io

        tar.addfile(info, io.BytesIO(data))


def _seed_all(root: Path) -> None:
    """A full, healthy set of latest backups (one of each kind)."""
    _write_gz(root / "postgres" / "minder_postgres_20260813_020001.sql.gz")
    _write_gz(root / "redis" / "minder_redis_20260813_020001.rdb.gz")
    _write_targz(root / "neo4j" / "neo4j_20260813_020001.tar.gz")
    _write_targz(root / "snapshots" / "minder_snapshot_20260813_020001.tar.gz")


def _run(root: Path, *args: str, max_age="26", min_bytes="100"):
    env = {
        **os.environ,
        # forward slashes so the path globs under Git Bash on Windows too (POSIX
        # hosts — the Pi, CI — are unaffected)
        "MINDER_BACKUP_DIR": root.as_posix(),
        "BACKUP_MAX_AGE_HOURS": max_age,
        "BACKUP_MIN_BYTES": min_bytes,
    }
    return subprocess.run(
        ["bash", str(_SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_all_backups_present_and_valid_pass(tmp_path):
    _seed_all(tmp_path)
    r = _run(tmp_path, "--quick")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RESULT: OK" in r.stdout
    assert r.stdout.count("[ OK ]") == 4


def test_bare_invocation_runs_quick(tmp_path):
    _seed_all(tmp_path)
    assert _run(tmp_path).returncode == 0


def test_missing_one_kind_fails(tmp_path):
    _seed_all(tmp_path)
    for p in (tmp_path / "neo4j").glob("*"):
        p.unlink()
    r = _run(tmp_path, "--quick")
    assert r.returncode == 1
    assert "[FAIL] neo4j: no backup" in r.stdout


def test_stale_backup_fails(tmp_path):
    _seed_all(tmp_path)
    old = time.time() - 3 * 24 * 3600  # 3 days ago
    for p in (tmp_path / "postgres").glob("*"):
        os.utime(p, (old, old))
    r = _run(tmp_path, "--quick")
    assert r.returncode == 1
    assert "[FAIL] postgres" in r.stdout and "old" in r.stdout


def test_truncated_backup_fails(tmp_path):
    _seed_all(tmp_path)
    # a 5-byte file is below the min-bytes floor
    (tmp_path / "redis" / "minder_redis_20260813_020001.rdb.gz").write_bytes(b"aaaaa")
    r = _run(tmp_path, "--quick", min_bytes="100")
    assert r.returncode == 1
    assert "[FAIL] redis" in r.stdout


def test_corrupt_archive_fails(tmp_path):
    _seed_all(tmp_path)
    # valid size + recent, but not a real gzip → integrity check must catch it
    (tmp_path / "postgres" / "minder_postgres_20260813_020001.sql.gz").write_bytes(
        b"not a gzip stream at all" * 20
    )
    r = _run(tmp_path, "--quick")
    assert r.returncode == 1
    assert "[FAIL] postgres" in r.stdout and "integrity" in r.stdout


def test_bad_arg_is_usage_error(tmp_path):
    _seed_all(tmp_path)
    r = _run(tmp_path, "--bogus")
    assert r.returncode == 2
