"""Unit tests for restore's corrupt-archive guard + skipped-store tracking
(restore.py, #281/#282/#283). No Docker: container probes, docker.run/compose,
and the un-gated psql/rabbitmqctl helpers are stubbed. Archives are real
tar.gz files built in tmp_path so tarfile extraction runs for real.
"""

import tarfile

import pytest

from scripts.setup import restore


def _make_archive(tmp_path, name="minder-20200101-000000", files=None):
    """Build a real `minder-<ts>.tar.gz` with the given {filename: contents}."""
    src = tmp_path / name
    src.mkdir()
    for fname, contents in (files or {}).items():
        (src / fname).write_text(contents)
    archive = tmp_path / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(src, arcname=name)
    return archive


@pytest.fixture
def stubbed(monkeypatch):
    monkeypatch.setattr(restore.config, "INTERACTIVE", False)
    monkeypatch.setattr(restore.config, "DRY_RUN", False)
    monkeypatch.setattr(restore.docker, "container_running", lambda s: True)
    monkeypatch.setattr(restore.docker, "container_name", lambda s: f"minder-{s}")
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: 0)
    monkeypatch.setattr(restore.docker, "compose", lambda *a, **k: 0)
    monkeypatch.setattr(restore.docker, "wait_postgres_ready", lambda *a, **k: True)
    monkeypatch.setattr(restore, "_restore_postgres", lambda *a, **k: True)
    monkeypatch.setattr(restore, "_run_bare", lambda *a, **k: 0)
    warns: list[str] = []
    succs: list[str] = []
    errors: list[str] = []
    monkeypatch.setattr(restore.log, "warn", lambda m: warns.append(m))
    monkeypatch.setattr(restore.log, "success", lambda m: succs.append(m))
    monkeypatch.setattr(restore.log, "error", lambda m: errors.append(m))
    for fn in ("section", "detail", "spinner_start", "spinner_stop"):
        monkeypatch.setattr(restore.log, fn, lambda *a, **k: None)
    return warns, succs, errors


def test_corrupt_archive_errors_instead_of_silent_noop(stubbed, tmp_path):
    """#283: an archive with no top-level backup directory (corrupt/truncated)
    must error out — not fall through to "Restore complete" having restored
    nothing."""
    warns, succs, errors = stubbed
    archive = tmp_path / "minder-broken.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo("stray-file.txt")
        info.size = 0
        tf.addfile(info)

    rc = restore.run(str(archive))

    assert rc == 1
    assert any("did not extract to a valid backup directory" in e for e in errors)
    assert not any("Restore complete" in s for s in succs)


def test_full_restore_reports_clean_success(monkeypatch, stubbed, tmp_path):
    archive = _make_archive(
        tmp_path,
        files={
            "env.backup": "X=1\n",
            "postgres.sql": "-- dump\n",
            "neo4j.cypher": "MATCH () RETURN 1;\n",
            "influxdb.tar.gz": "fake",
            "qdrant.tar.gz": "fake",
            "rabbitmq-definitions.json": "{}",
        },
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("Restore complete — restart services" in s for s in succs)
    assert not any("NOT restored" in w for w in warns)


def test_not_running_store_is_tracked_as_skipped(monkeypatch, stubbed, tmp_path):
    """#282: archived data exists but its container isn't running — must be
    surfaced in the final summary, not silently dropped."""
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "qdrant.tar.gz": "fake",
        },
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")

    def container_running(service):
        return service != "qdrant"

    monkeypatch.setattr(restore.docker, "container_running", container_running)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("Qdrant not running — restore skipped" in w for w in warns)
    assert any("Restore complete — NOT restored: Qdrant" in w for w in warns)


def test_failed_store_restore_is_tracked_as_skipped(monkeypatch, stubbed, tmp_path):
    """#282: a store whose restore itself fails (not just "not running") must
    also land in the final NOT-restored summary."""
    archive = _make_archive(
        tmp_path,
        files={"postgres.sql": "-- dump\n"},
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    monkeypatch.setattr(restore, "_restore_postgres", lambda *a, **k: False)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("PostgreSQL restore had errors" in w for w in warns)
    assert any("Restore complete — NOT restored: PostgreSQL" in w for w in warns)
