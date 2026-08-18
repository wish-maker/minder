"""Additional unit tests for scripts/setup/restore.py's remaining branches --
test_setup_restore.py already covers the #281/#282/#283/#288/#289/#643/#644
regression guards; this file covers everything else that was still at 68%:
_select_archive, the interactive confirm/cancel path, DRY_RUN previews for
every store, the not-running/had-errors branches for InfluxDB/Qdrant/MinIO/
RabbitMQ, _restore_postgres's OSError branches, _run_bare, and
_safe_extract_members' link-escape rejection. No Docker: subprocess/docker
are mocked; archives are real tar.gz files built in tmp_path.
"""

import io
import tarfile

import pytest

from scripts.setup import restore


def _make_archive(tmp_path, name="minder-20200101-000000", files=None):
    src = tmp_path / name
    src.mkdir()
    for fname, contents in (files or {}).items():
        (src / fname).write_bytes(
            contents if isinstance(contents, bytes) else contents.encode()
        )
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
    monkeypatch.setattr(restore.docker, "wait_healthy", lambda *a, **k: True)
    monkeypatch.setattr(restore, "_restore_postgres", lambda *a, **k: True)
    monkeypatch.setattr(restore, "_run_bare", lambda *a, **k: 0)
    warns, succs, errors = [], [], []
    monkeypatch.setattr(restore.log, "warn", lambda m: warns.append(m))
    monkeypatch.setattr(restore.log, "success", lambda m: succs.append(m))
    monkeypatch.setattr(restore.log, "error", lambda m: errors.append(m))
    for fn in ("section", "detail", "spinner_start", "spinner_stop"):
        monkeypatch.setattr(restore.log, fn, lambda *a, **k: None)
    return warns, succs, errors


# ── run(): no-file / interactive confirm-cancel ───────────────────────────────


def test_run_errors_when_archive_file_missing(stubbed, tmp_path):
    warns, succs, errors = stubbed
    rc = restore.run(str(tmp_path / "does-not-exist.tar.gz"))
    assert rc == 1
    assert any("File not found" in e for e in errors)


def test_run_cancels_on_interactive_no(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "INTERACTIVE", True)
    archive = _make_archive(tmp_path, files={"postgres.sql": "-- dump\n"})
    infos = []
    monkeypatch.setattr(restore.log, "info", lambda m: infos.append(m))
    monkeypatch.setattr(restore.sys.stdin, "readline", lambda: "n\n")

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("cancelled" in m for m in infos)


def test_run_proceeds_on_interactive_yes(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "INTERACTIVE", True)
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(tmp_path, files={"postgres.sql": "-- dump\n"})
    monkeypatch.setattr(restore.sys.stdin, "readline", lambda: "y\n")

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("Restore complete" in s for s in succs)


def test_run_tolerates_a_raising_extraction(monkeypatch, stubbed, tmp_path):
    """A genuinely corrupt gzip stream raises inside tarfile.open/extractall --
    swallowed the same way bash's unguarded `tar xzf` would leave restore_dir
    empty, landing in the #283 corrupt-archive error path."""
    warns, succs, errors = stubbed
    archive = tmp_path / "corrupt.tar.gz"
    archive.write_bytes(b"not a real gzip stream")

    rc = restore.run(str(archive))

    assert rc == 1
    assert any("did not extract to a valid backup directory" in e for e in errors)


# ── _select_archive ────────────────────────────────────────────────────────────


def test_select_archive_errors_when_no_backups_found(monkeypatch, tmp_path, capfd):
    monkeypatch.setattr(restore.config, "BACKUP_DIR", tmp_path)
    errors = []
    monkeypatch.setattr(restore.log, "error", lambda m: errors.append(m))

    result = restore._select_archive()

    assert result is None
    assert any("No backups found" in e for e in errors)


def test_select_archive_errors_when_noninteractive_with_backups_present(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(restore.config, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(restore.config, "INTERACTIVE", False)
    (tmp_path / "minder-20200101-000000.tar.gz").write_bytes(b"x")
    monkeypatch.setattr(restore.backup, "_du_sh", lambda p: "1.0M")
    errors = []
    monkeypatch.setattr(restore.log, "error", lambda m: errors.append(m))

    result = restore._select_archive()

    assert result is None
    assert any("No backup archive specified" in e for e in errors)


def test_select_archive_interactive_picks_by_index(monkeypatch, tmp_path):
    monkeypatch.setattr(restore.config, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(restore.config, "INTERACTIVE", True)
    (tmp_path / "minder-20200101-000000.tar.gz").write_bytes(b"x")
    (tmp_path / "minder-20200202-000000.tar.gz").write_bytes(b"x")
    monkeypatch.setattr(restore.backup, "_du_sh", lambda p: "1.0M")
    monkeypatch.setattr(restore.sys.stdin, "readline", lambda: "1\n")

    result = restore._select_archive()

    # newest-first: 20200202 sorts before 20200101 in reverse order.
    assert result is not None
    assert "minder-20200202-000000.tar.gz" in result


def test_select_archive_interactive_out_of_range_returns_empty_string(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(restore.config, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(restore.config, "INTERACTIVE", True)
    (tmp_path / "minder-20200101-000000.tar.gz").write_bytes(b"x")
    monkeypatch.setattr(restore.backup, "_du_sh", lambda p: "1.0M")
    monkeypatch.setattr(restore.sys.stdin, "readline", lambda: "99\n")

    assert restore._select_archive() == ""


def test_select_archive_interactive_non_numeric_returns_empty_string(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(restore.config, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(restore.config, "INTERACTIVE", True)
    (tmp_path / "minder-20200101-000000.tar.gz").write_bytes(b"x")
    monkeypatch.setattr(restore.backup, "_du_sh", lambda p: "1.0M")
    monkeypatch.setattr(restore.sys.stdin, "readline", lambda: "abc\n")

    assert restore._select_archive() == ""


def test_run_with_no_archive_arg_errors_when_selection_aborted(monkeypatch, stubbed):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore, "_select_archive", lambda: None)

    rc = restore.run("")

    assert rc == 1


def test_run_with_no_archive_arg_uses_the_selected_path(monkeypatch, stubbed, tmp_path):
    """A non-None _select_archive() result must be adopted as `archive` and
    flow into the normal file-existence check right after."""
    warns, succs, errors = stubbed
    archive = _make_archive(tmp_path, files={"postgres.sql": "-- dump\n"})
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    monkeypatch.setattr(restore, "_select_archive", lambda: str(archive))

    rc = restore.run("")

    assert rc == 0
    assert any("Restore complete" in s for s in succs)


# ── DRY_RUN preview branches ───────────────────────────────────────────────────


def test_dry_run_env_restore_previews_cp_and_chmod(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "DRY_RUN", True)
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(tmp_path, files={"env.backup": "X=1\n"})
    calls = []
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any(c[0] == "cp" for c in calls)
    assert any(c[0] == "chmod" for c in calls)
    assert not (tmp_path / "env").exists()  # DRY_RUN never actually copies


def test_dry_run_postgres_restore_previews_psql_command(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "DRY_RUN", True)
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(tmp_path, files={"postgres.sql": "-- dump\n"})
    calls = []
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("psql" in c for c in calls)
    assert any("PostgreSQL restored" in s for s in succs)


def test_dry_run_neo4j_previews_clear_and_import(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "DRY_RUN", True)
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path,
        files={"postgres.sql": "-- dump\n", "neo4j.cypher": "CREATE (:X);\n"},
    )
    calls = []
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("DETACH DELETE" in " ".join(c) for c in calls)
    assert any("Neo4j restored" in s for s in succs)


def test_dry_run_rabbitmq_previews_import_definitions(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "DRY_RUN", True)
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "rabbitmq-definitions.json": "{}",
        },
    )
    calls = []
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("import_definitions" in " ".join(c) for c in calls)
    assert any("RabbitMQ definitions restored" in s for s in succs)


# ── not-running / had-errors branches for InfluxDB/Qdrant/MinIO/RabbitMQ ──────


def test_influxdb_not_running_is_tracked_as_skipped(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path, files={"postgres.sql": "-- dump\n", "influxdb.tar.gz": "fake"}
    )
    monkeypatch.setattr(restore.docker, "container_running", lambda s: s != "influxdb")

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("InfluxDB not running — restore skipped" in w for w in warns)
    assert any("NOT restored: InfluxDB" in w for w in warns)


def test_influxdb_restore_success(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path, files={"postgres.sql": "-- dump\n", "influxdb.tar.gz": "fake"}
    )

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("InfluxDB restored" in s for s in succs)


def test_influxdb_restore_had_errors(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path, files={"postgres.sql": "-- dump\n", "influxdb.tar.gz": "fake"}
    )
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: 1)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("InfluxDB restore had errors" in w for w in warns)
    assert any("NOT restored: InfluxDB" in w for w in warns)


def test_qdrant_restore_had_errors(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path, files={"postgres.sql": "-- dump\n", "qdrant.tar.gz": "fake"}
    )
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: 1)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("Qdrant restore had errors" in w for w in warns)


def test_neo4j_not_running_is_tracked_as_skipped(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path, files={"postgres.sql": "-- dump\n", "neo4j.cypher": "CREATE (:X);\n"}
    )
    monkeypatch.setattr(restore.docker, "container_running", lambda s: s != "neo4j")

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("Neo4j not running — restore skipped" in w for w in warns)


def test_minio_restore_had_errors_when_docker_cp_fails(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")

    def _make_minio_inner(tmp_path):
        src = tmp_path / "_minio_src" / "minio_data_raw"
        src.mkdir(parents=True)
        (src / "f").write_bytes(b"data")
        inner = tmp_path / "_inner.tar.gz"
        with tarfile.open(inner, "w:gz") as tf:
            tf.add(src, arcname="minio_data_raw")
        return inner.read_bytes()

    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "minio.tar.gz": _make_minio_inner(tmp_path),
        },
    )
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: 1)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("MinIO restore had errors" in w for w in warns)


def test_minio_restore_had_errors_on_bad_inner_archive(monkeypatch, stubbed, tmp_path):
    """The inner minio.tar.gz itself is corrupt -- must land in the had-errors
    branch (caught OSError/TarError), not crash the whole restore."""
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path,
        files={"postgres.sql": "-- dump\n", "minio.tar.gz": b"not a real tar.gz"},
    )

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("MinIO restore had errors" in w for w in warns)


def test_rabbitmq_restore_had_errors(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "rabbitmq-definitions.json": "{}",
        },
    )
    monkeypatch.setattr(restore, "_run_bare", lambda *a, **k: 1)

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("RabbitMQ definitions restore had errors" in w for w in warns)


def test_rabbitmq_not_running_is_tracked_as_skipped(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "rabbitmq-definitions.json": "{}",
        },
    )
    monkeypatch.setattr(restore.docker, "container_running", lambda s: s != "rabbitmq")

    rc = restore.run(str(archive))

    assert rc == 0
    assert any("RabbitMQ not running — restore skipped" in w for w in warns)


# ── env restore chmod OSError tolerance ────────────────────────────────────────


def test_env_restore_tolerates_chmod_oserror(monkeypatch, stubbed, tmp_path):
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    archive = _make_archive(tmp_path, files={"env.backup": "X=1\n"})
    monkeypatch.setattr(
        restore.Path, "chmod", lambda self, mode: (_ for _ in ()).throw(OSError("no"))
    )

    rc = restore.run(str(archive))

    assert rc == 0
    assert any(".env restored" in s for s in succs)


# ── _run_bare ──────────────────────────────────────────────────────────────────


def test_run_bare_returns_returncode(monkeypatch):
    monkeypatch.setattr(
        restore.subprocess, "run", lambda argv, **kw: type("R", (), {"returncode": 3})()
    )
    assert restore._run_bare(["echo", "hi"]) == 3


def test_run_bare_returns_127_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("docker not found")

    monkeypatch.setattr(restore.subprocess, "run", _raise)
    assert restore._run_bare(["docker", "ps"]) == 127


def test_run_bare_stderr_null_redirects(monkeypatch):
    captured = {}

    def _fake_run(argv, **kw):
        captured.update(kw)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(restore.subprocess, "run", _fake_run)
    restore._run_bare(["echo", "hi"], stderr_null=True)
    assert captured["stderr"] == restore.subprocess.DEVNULL


# ── _restore_postgres OSError branches ────────────────────────────────────────


def test_restore_postgres_returns_false_when_popen_raises(monkeypatch, tmp_path):
    sql = tmp_path / "postgres.sql"
    sql.write_bytes(b"SELECT 1;\n")
    monkeypatch.setattr(restore.docker, "container_name", lambda s: "minder-postgres")

    def _raise(*a, **k):
        raise OSError("docker not found")

    monkeypatch.setattr(restore.subprocess, "Popen", _raise)
    assert restore._restore_postgres(sql) is False


def test_restore_postgres_tolerates_broken_pipe_mid_write(monkeypatch, tmp_path):
    sql = tmp_path / "postgres.sql"
    sql.write_bytes(b"SELECT 1;\nSELECT 2;\n")
    monkeypatch.setattr(restore.docker, "container_name", lambda s: "minder-postgres")

    class _FailingStdin:
        def write(self, b):
            raise OSError("broken pipe")

        def close(self):
            pass

    class _Proc:
        stdin = _FailingStdin()

        def wait(self):
            return 1

    monkeypatch.setattr(restore.subprocess, "Popen", lambda *a, **k: _Proc())

    assert restore._restore_postgres(sql) is False  # must not raise


def test_restore_postgres_tolerates_stdin_close_oserror(monkeypatch, tmp_path):
    sql = tmp_path / "postgres.sql"
    sql.write_bytes(b"SELECT 1;\n")
    monkeypatch.setattr(restore.docker, "container_name", lambda s: "minder-postgres")

    class _FailingCloseStdin:
        def write(self, b):
            pass

        def close(self):
            raise OSError("already closed")

    class _Proc:
        stdin = _FailingCloseStdin()

        def wait(self):
            return 0

    monkeypatch.setattr(restore.subprocess, "Popen", lambda *a, **k: _Proc())

    assert restore._restore_postgres(sql) is True


# ── _safe_extract_members: link-escape rejection ──────────────────────────────


def test_safe_extract_members_rejects_a_symlink_escaping_the_dest(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    archive = tmp_path / "evil-link.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        link_info = tarfile.TarInfo("escape-link")
        link_info.type = tarfile.SYMTYPE
        link_info.linkname = "../../outside"
        tf.addfile(link_info)
        safe_info = tarfile.TarInfo("safe.txt")
        data = b"safe"
        safe_info.size = len(data)
        tf.addfile(safe_info, io.BytesIO(data))

    with tarfile.open(archive, "r:gz") as tf:
        members = restore._safe_extract_members(tf, dest)

    names = [m.name for m in members]
    assert "escape-link" not in names
    assert "safe.txt" in names
