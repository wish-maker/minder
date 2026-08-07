"""Unit tests for backup's incomplete-summary + InfluxDB capture (backup.py).

#177: a RUNNING datastore that isn't captured must no longer read as a clean
"Backup complete" (loud warn listing what's missing), AND InfluxDB is now
captured via a token-free raw data-dir snapshot (the v2 `influx backup` CLI is
absent from influxdb 3-core), so it's no longer silently skipped. No Docker: the
container probes, docker.run, and the un-gated dump/archive helpers are stubbed.
"""

import pytest

from scripts.setup import backup


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
