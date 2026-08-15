"""Unit tests for backup's incomplete-summary + InfluxDB capture (backup.py).

#177: a RUNNING datastore that isn't captured must no longer read as a clean
"Backup complete" (loud warn listing what's missing), AND InfluxDB is now
captured via a token-free raw data-dir snapshot (the v2 `influx backup` CLI is
absent from influxdb 3-core), so it's no longer silently skipped. No Docker: the
container probes, docker.run, and the un-gated dump/archive helpers are stubbed.
"""

import sys

import pytest

from scripts.setup import backup

# The secret-permission tests assert exact POSIX file modes (0o700/0o600). Windows
# (NTFS) can't represent those — os.chmod only toggles the read-only bit — so they
# spuriously fail on a Windows dev machine while passing in CI (Linux). Skip them
# there; the CI gate on ubuntu-latest still enforces the real permission contract.
_posix_perms_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX file modes (0o700/0o600) aren't representable on Windows/NTFS",
)


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    monkeypatch.setattr(backup.config, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(backup.config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setattr(backup.config, "DRY_RUN", False)
    monkeypatch.setattr(backup.docker, "container_running", lambda s: True)
    monkeypatch.setattr(backup.docker, "container_name", lambda s: f"minder-{s}")
    monkeypatch.setattr(backup.docker, "run", lambda *a, **k: 0)
    monkeypatch.setattr(backup, "_dump_to_file", lambda *a, **k: True)
    monkeypatch.setattr(backup, "_make_archive", lambda *a, **k: True)
    warns: list[str] = []
    succs: list[str] = []
    monkeypatch.setattr(backup.log, "warn", lambda m: warns.append(m))
    monkeypatch.setattr(backup.log, "success", lambda m: succs.append(m))
    for fn in ("section", "detail", "spinner_start", "spinner_stop"):
        monkeypatch.setattr(backup.log, fn, lambda *a, **k: None)
    return warns, succs


def test_all_captured_reports_clean_success(stubbed):
    """Every running store captured (incl. InfluxDB, token-free) → clean success."""
    warns, succs = stubbed
    rc = backup.run()
    assert rc == 0
    assert "Backup complete" in succs
    assert not any("NOT captured" in w for w in warns)


def test_influx_snapshot_is_token_free(monkeypatch, stubbed):
    """InfluxDB is snapshotted via a raw tar of its data dir — no token lookup,
    no `influx backup` CLI (#177)."""
    calls: list[tuple] = []
    monkeypatch.setattr(backup.docker, "run", lambda *cmd, **k: calls.append(cmd) or 0)
    backup.run()
    flat = [" ".join(str(a) for a in c) for c in calls]
    assert any("/var/lib/influxdb3" in f and "tar" in f for f in flat)
    assert not any("influx backup" in f or "--token" in f for f in flat)


def test_influx_snapshot_failure_is_loud(monkeypatch, stubbed):
    """A failed InfluxDB snapshot (running store) surfaces in the final line."""
    warns, succs = stubbed

    def run(*cmd, **k):
        return 1 if "/var/lib/influxdb3" in cmd else 0

    monkeypatch.setattr(backup.docker, "run", run)
    rc = backup.run()
    assert rc == 0
    assert any("Backup complete — NOT captured: InfluxDB" in w for w in warns)


def test_running_store_failure_marked(monkeypatch, stubbed):
    warns, _ = stubbed
    monkeypatch.setattr(
        backup, "_dump_to_file", lambda *a, **k: False
    )  # postgres fails
    backup.run()
    assert any("Backup complete — NOT captured: PostgreSQL" in w for w in warns)


def test_minio_snapshot_targets_data_dir(monkeypatch, stubbed):
    """MinIO is snapshotted via a raw tar of its /data dir (mirrors Qdrant's
    /qdrant/storage pattern) -- was a silent gap before this."""
    calls: list[tuple] = []
    monkeypatch.setattr(backup.docker, "run", lambda *cmd, **k: calls.append(cmd) or 0)
    backup.run()
    flat = [" ".join(str(a) for a in c) for c in calls]
    assert any("/data" in f and "tar" in f and "minio" in f.lower() for f in flat)


def test_minio_snapshot_failure_is_loud(monkeypatch, stubbed):
    """A failed MinIO snapshot (running store) surfaces in the final line."""
    warns, _ = stubbed

    def run(*cmd, **k):
        # Match the "docker cp minder-minio:/data ..." call specifically --
        # the container ref is embedded in a combined "name:/data" string
        # arg (not a standalone tuple element), and tmp_path (used for
        # config.BACKUP_DIR) contains this test's own name as a substring, so
        # a loose "minio" check would false-positive-match every docker.run
        # call's destination-path argument, not just the MinIO one.
        return 1 if any(str(a).startswith("minder-minio:") for a in cmd) else 0

    monkeypatch.setattr(backup.docker, "run", run)
    rc = backup.run()
    assert rc == 0
    assert any("Backup complete — NOT captured: MinIO" in w for w in warns)


# ── Secret-handling permissions (found in a background audit) ────────────────
# Only env.backup ever got a chmod -- the staging dir, the PostgreSQL dump
# (which includes CREATE ROLE ... PASSWORD hashes via bare pg_dumpall, no
# --no-role-passwords), and the final archive all landed with ordinary
# umask-based permissions. These lock in the fix.


@_posix_perms_only
def test_staging_dir_is_chmod_700(monkeypatch, stubbed, tmp_path):
    # _make_archive returns False (the "compression failed, uncompressed
    # backup kept" fallback) so the staging dir survives rmtree for
    # inspection -- the default stub's "successful" compress (of a no real
    # archive ever written) still rmtree's it same as a genuine success would.
    monkeypatch.setattr(backup, "_make_archive", lambda *a, **k: False)

    backup.run()

    staging_dirs = [
        p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("minder-")
    ]
    assert len(staging_dirs) == 1
    assert (staging_dirs[0].stat().st_mode & 0o777) == 0o700


@_posix_perms_only
def test_postgres_dump_is_chmod_600(monkeypatch, stubbed, tmp_path):
    def fake_dump_to_file(argv, dest_file):
        dest_file.write_bytes(b"-- dump with CREATE ROLE ... PASSWORD 'x'\n")
        return True

    monkeypatch.setattr(backup, "_dump_to_file", fake_dump_to_file)
    # _make_archive returns False here (the "compression failed, uncompressed
    # backup kept" fallback) so the staging dir -- with the real dump file
    # inside it -- survives for inspection instead of being rmtree'd after a
    # (stubbed, no real archive written) "successful" compress.
    monkeypatch.setattr(backup, "_make_archive", lambda *a, **k: False)

    backup.run()

    staging_dirs = [
        p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("minder-")
    ]
    dump = staging_dirs[0] / "postgres.sql"
    assert dump.is_file()
    assert (dump.stat().st_mode & 0o777) == 0o600


@_posix_perms_only
def test_archive_is_chmod_600(monkeypatch, stubbed, tmp_path):
    def fake_make_archive(archive, base_dir, name):
        archive.write_bytes(b"fake-archive-bytes")
        return True

    monkeypatch.setattr(backup, "_make_archive", fake_make_archive)

    backup.run()

    archives = list(tmp_path.glob("minder-*.tar.gz"))
    assert len(archives) == 1
    assert (archives[0].stat().st_mode & 0o777) == 0o600
