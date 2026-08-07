"""Unit tests for restore's corrupt-archive guard, skipped-store tracking,
network-recreation-before-postgres, and own-role-statement stripping
(restore.py, #281/#282/#283/#288/#289). No Docker: container probes,
docker.run/compose, and the un-gated psql/rabbitmqctl helpers are stubbed.
Archives are real tar.gz files built in tmp_path so tarfile extraction runs
for real.
"""

import tarfile

import pytest

from scripts.setup import restore

_REAL_RESTORE_POSTGRES = restore._restore_postgres


def _make_archive(tmp_path, name="minder-20200101-000000", files=None):
    """Build a real `minder-<ts>.tar.gz` with the given {filename: contents}."""
    src = tmp_path / name
    src.mkdir()
    for fname, contents in (files or {}).items():
        # write_text() translates "\n" -> os.linesep on write, corrupting the
        # LF-only dump fixture with CRLF on Windows before restore.py ever
        # reads it (a real dump's bytes come straight off docker exec's
        # stdout via backup.py's open(..., "wb"), never through Windows text-
        # mode translation) -- write_bytes keeps this fixture host-independent.
        (src / fname).write_bytes(contents.encode())
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
            "minio.tar.gz": "fake",
            "rabbitmq-definitions.json": "{}",
        },
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("Restore complete — restart services" in s for s in succs)
    assert not any("NOT restored" in w for w in warns)


def test_extract_falls_back_when_filter_kwarg_unsupported(
    monkeypatch, stubbed, tmp_path
):
    """Found live on the Pi: Python 3.11.2 predates PEP 706's `filter` kwarg on
    TarFile.extractall, so it raised an unhandled TypeError on every restore
    instead of ever reaching the corrupt-archive handling. Must fall back to
    an unfiltered extract (these are our own backup archives, not untrusted
    uploads) rather than crash."""
    archive = _make_archive(tmp_path, files={"postgres.sql": "-- dump\n"})
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")

    real_extractall = tarfile.TarFile.extractall

    def fake_extractall(self, path, *args, **kwargs):
        if "filter" in kwargs:
            raise TypeError("extractall() got an unexpected keyword argument 'filter'")
        return real_extractall(self, path, *args, **kwargs)

    monkeypatch.setattr(tarfile.TarFile, "extractall", fake_extractall)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("Restore complete — restart services" in s for s in succs)


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


def test_minio_not_running_is_tracked_as_skipped(monkeypatch, stubbed, tmp_path):
    """Mirrors the Qdrant #282 test above -- archived MinIO data exists but its
    container isn't running."""
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "minio.tar.gz": "fake",
        },
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")

    def container_running(service):
        return service != "minio"

    monkeypatch.setattr(restore.docker, "container_running", container_running)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("MinIO not running — restore skipped" in w for w in warns)
    assert any("Restore complete — NOT restored: MinIO" in w for w in warns)


def test_minio_restore_copies_in_and_extracts_same_archive(
    monkeypatch, stubbed, tmp_path
):
    """Mirrors the Qdrant #56 fix -- must copy in AND extract the SAME
    /tmp/minio.tar.gz, not a stale/absent filename (the bug #56 fixed for
    Qdrant, avoided here from the start)."""
    archive = _make_archive(
        tmp_path,
        files={"postgres.sql": "-- dump\n", "minio.tar.gz": "fake"},
    )
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    calls: list[tuple] = []
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    cp_calls = [c for c in calls if c[:2] == ("docker", "cp")]
    exec_calls = [c for c in calls if c[:3] == ("docker", "exec", "minder-minio")]
    assert any("/tmp/minio.tar.gz" in str(c) for c in cp_calls)
    assert any(
        "tar" in c and "xzf" in c and "/tmp/minio.tar.gz" in c for c in exec_calls
    )


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


def test_postgres_not_running_recreates_network_first(monkeypatch, stubbed, tmp_path):
    """#288: found live on hantal — restore's own precondition is "services must
    be stopped", and `stop` deliberately removes the app network, so bringing
    postgres back up here must recreate the network first (mirroring
    start.py) or `compose up -d postgres` fails with "network ... declared as
    external, but could not be found"."""
    archive = _make_archive(tmp_path, files={"postgres.sql": "-- dump\n"})
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")

    def container_running(service):
        return service != "postgres"

    monkeypatch.setattr(restore.docker, "container_running", container_running)
    calls: list[str] = []
    monkeypatch.setattr(
        restore.infra, "create_networks", lambda: calls.append("create_networks")
    )
    monkeypatch.setattr(restore.docker, "compose", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    assert calls[0] == "create_networks"
    assert ("up", "-d", "postgres") in calls[1:]


def test_strip_own_role_statements_removes_only_bootstrap_role_lines():
    """#289: found live on hantal — pg_dumpall --clean's `DROP/CREATE/ALTER
    ROLE minder` can never succeed (minder is both the only role and the one
    the restore connects as), so ON_ERROR_STOP would hard-abort the restore
    before any real data is touched. Other roles/statements must survive."""
    dump = (
        b"-- Drop roles\n"
        b"DROP ROLE IF EXISTS minder;\n"
        b"DROP ROLE IF EXISTS readonly_reporter;\n"
        b"CREATE ROLE minder;\n"
        b"ALTER ROLE minder WITH SUPERUSER LOGIN PASSWORD 'x';\n"
        b"CREATE ROLE readonly_reporter;\n"
        b"DROP DATABASE IF EXISTS minder;\n"
        b"CREATE DATABASE minder;\n"
    )
    filtered = restore._strip_own_role_statements(dump)
    assert b"minder;\n" not in filtered.replace(
        b"DROP DATABASE IF EXISTS minder;\n", b""
    ).replace(b"CREATE DATABASE minder;\n", b"")
    assert b"DROP ROLE IF EXISTS readonly_reporter;\n" in filtered
    assert b"CREATE ROLE readonly_reporter;\n" in filtered
    assert b"DROP DATABASE IF EXISTS minder;\n" in filtered
    assert b"CREATE DATABASE minder;\n" in filtered
    assert b"DROP ROLE IF EXISTS minder;\n" not in filtered
    assert b"CREATE ROLE minder;\n" not in filtered
    assert b"ALTER ROLE minder WITH SUPERUSER LOGIN PASSWORD 'x';\n" not in filtered


def test_postgres_restore_strips_own_role_statements_before_psql(
    monkeypatch, stubbed, tmp_path
):
    """#289: `_restore_postgres` must feed the FILTERED dump to psql, not the
    raw file — otherwise ON_ERROR_STOP aborts on the bootstrap role's own
    always-failing DROP/CREATE/ALTER ROLE statements."""
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": (
                "DROP ROLE IF EXISTS minder;\n"
                "CREATE ROLE minder;\n"
                "ALTER ROLE minder WITH SUPERUSER LOGIN PASSWORD 'x';\n"
                "DROP DATABASE IF EXISTS minder;\n"
            )
        },
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    monkeypatch.setattr(restore, "_restore_postgres", _REAL_RESTORE_POSTGRES)
    captured: dict = {}

    def fake_run(argv, input=None, **kwargs):
        captured["input"] = input

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(restore.subprocess, "run", fake_run)

    rc = restore.run(str(archive))

    assert rc == 0
    assert b"minder;\n" not in captured["input"].replace(
        b"DROP DATABASE IF EXISTS minder;\n", b""
    )
    assert b"DROP DATABASE IF EXISTS minder;\n" in captured["input"]
