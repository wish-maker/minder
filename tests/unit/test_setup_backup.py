"""Unit tests for backup's incomplete-summary (scripts/setup/backup.py).

#177: a RUNNING datastore that isn't captured (export failed, or skipped for a
missing credential) must no longer read as a clean "Backup complete". The final
line switches to a loud warn listing what's missing. No Docker: the container
probes, docker.run, and the un-gated dump/archive helpers are stubbed.
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


def test_influx_token_missing_is_loud(monkeypatch, stubbed):
    warns, succs = stubbed
    monkeypatch.setattr(backup.env, "get", lambda k: "")  # no INFLUXDB_ADMIN_TOKEN
    rc = backup.run()
    assert rc == 0  # still non-fatal
    assert any("Backup complete — NOT captured: InfluxDB" in w for w in warns)
    assert "Backup complete" not in succs  # not the clean-success form


def test_all_captured_reports_clean_success(monkeypatch, stubbed):
    warns, succs = stubbed
    monkeypatch.setattr(backup.env, "get", lambda k: "tok")
    rc = backup.run()
    assert rc == 0
    assert "Backup complete" in succs
    assert not any("NOT captured" in w for w in warns)


def test_running_store_failure_marked(monkeypatch, stubbed):
    warns, _ = stubbed
    monkeypatch.setattr(backup.env, "get", lambda k: "tok")  # influx fine
    monkeypatch.setattr(
        backup, "_dump_to_file", lambda *a, **k: False
    )  # postgres fails
    backup.run()
    assert any("Backup complete — NOT captured: PostgreSQL" in w for w in warns)
