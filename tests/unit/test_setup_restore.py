"""Unit tests for restore's corrupt-archive guard, skipped-store tracking,
network-recreation-before-postgres, and own-role-statement stripping
(restore.py, #281/#282/#283/#288/#289). No Docker: container probes,
docker.run/compose, and the un-gated psql/rabbitmqctl helpers are stubbed.
Archives are real tar.gz files built in tmp_path so tarfile extraction runs
for real.
"""

import shutil
import tarfile

import pytest

from scripts.setup import restore

_REAL_RESTORE_POSTGRES = restore._restore_postgres


def _make_archive(tmp_path, name="minder-20200101-000000", files=None):
    """Build a real `minder-<ts>.tar.gz` with the given {filename: contents}.
    `contents` may be a str (encoded) or raw bytes (written as-is -- needed for
    minio.tar.gz, which restore.py now actually tarfile.opens, unlike the other
    per-store archives which just get docker-cp'd/exec'd opaquely)."""
    src = tmp_path / name
    src.mkdir()
    for fname, contents in (files or {}).items():
        # write_text() translates "\n" -> os.linesep on write, corrupting the
        # LF-only dump fixture with CRLF on Windows before restore.py ever
        # reads it (a real dump's bytes come straight off docker exec's
        # stdout via backup.py's open(..., "wb"), never through Windows text-
        # mode translation) -- write_bytes keeps this fixture host-independent.
        (src / fname).write_bytes(
            contents if isinstance(contents, bytes) else contents.encode()
        )
    archive = tmp_path / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(src, arcname=name)
    return archive


def _make_minio_inner_archive(tmp_path):
    """A real nested tar.gz shaped like backup.py's MinIO output: a top-level
    'minio_data_raw' dir (the raw tree `docker cp`'d out of the container's
    /data). restore.py now tarfile.opens minio.tar.gz for real (host-side
    extraction, since MinIO's image has no `tar` binary), so a placeholder
    string like "fake" is no longer good enough wherever a container IS
    running and the extraction actually executes."""
    src = tmp_path / "_minio_src" / "minio_data_raw"
    src.mkdir(parents=True)
    (src / "somefile").write_bytes(b"bucket-data")
    inner = tmp_path / "_minio_inner.tar.gz"
    with tarfile.open(inner, "w:gz") as tf:
        tf.add(src, arcname="minio_data_raw")
    data = inner.read_bytes()
    inner.unlink()
    shutil.rmtree(tmp_path / "_minio_src")
    return data


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
            "minio.tar.gz": _make_minio_inner_archive(tmp_path),
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
    surfaced in the final summary, not silently dropped. Also confirms the
    background-audit fix: bringing qdrant up is actually ATTEMPTED first
    (_ensure_running) -- it only stays skipped here because the test's own
    container_running mock is unconditionally False for qdrant, standing in
    for a real environment where `compose up` didn't actually succeed."""
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
    calls: list[tuple] = []
    monkeypatch.setattr(restore.docker, "compose", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    assert ("up", "-d", "qdrant") in calls
    assert any("Qdrant not running — restore skipped" in w for w in warns)
    assert any("Restore complete — NOT restored: Qdrant" in w for w in warns)


def test_minio_not_running_is_tracked_as_skipped(monkeypatch, stubbed, tmp_path):
    """Mirrors the Qdrant #282 test above -- archived MinIO data exists but its
    container isn't running. Also confirms bringing it up is attempted first
    (_ensure_running), same background-audit fix as the Qdrant test above."""
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
    calls: list[tuple] = []
    monkeypatch.setattr(restore.docker, "compose", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    assert ("up", "-d", "minio") in calls
    assert any("MinIO not running — restore skipped" in w for w in warns)
    assert any("Restore complete — NOT restored: MinIO" in w for w in warns)


def test_minio_restore_copies_in_and_extracts_same_archive(
    monkeypatch, stubbed, tmp_path
):
    """MinIO's image has no `tar` binary (found live on the Pi via backup.py),
    so restore extracts minio.tar.gz host-side via Python tarfile and pushes
    the resulting tree into the container with a single `docker cp`, instead
    of the docker-exec-tar approach every other store uses."""
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "minio.tar.gz": _make_minio_inner_archive(tmp_path),
        },
    )
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    calls: list[tuple] = []
    monkeypatch.setattr(restore.docker, "run", lambda *a, **k: calls.append(a) or 0)

    rc = restore.run(str(archive))

    assert rc == 0
    cp_calls = [c for c in calls if c[:2] == ("docker", "cp")]
    assert any(
        "minio_data_raw" in str(c[2]) and c[3] == "minder-minio:/data" for c in cp_calls
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


def test_neo4j_restore_clears_graph_before_import(monkeypatch, stubbed, tmp_path):
    """#643: the export uses CREATE (not MERGE), so restoring onto a non-empty
    graph would duplicate every node/rel. Restore must issue a DETACH DELETE
    clear BEFORE the -f import, and the import must only run if the clear
    succeeded (else duplication is reintroduced)."""
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "neo4j.cypher": "CREATE (:X);\n",
        },
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    bare_calls: list[list] = []
    monkeypatch.setattr(
        restore, "_run_bare", lambda cmd, **k: bare_calls.append(cmd) or 0
    )

    rc = restore.run(str(archive))

    assert rc == 0
    joined = ["\n".join(c) for c in bare_calls]
    clear_idx = next(i for i, s in enumerate(joined) if "DETACH DELETE" in s)
    import_idx = next(i for i, s in enumerate(joined) if "neo4j-restore.cypher" in s)
    assert clear_idx < import_idx, "graph must be cleared before the import runs"
    assert any("Neo4j restored" in s for s in succs)


def test_neo4j_restore_skips_import_when_clear_fails(monkeypatch, stubbed, tmp_path):
    """If the DETACH DELETE clear fails, restore must NOT import onto the
    unemptied graph (that would reintroduce the #643 duplication) — it marks
    Neo4j skipped instead."""
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": "-- dump\n",
            "neo4j.cypher": "CREATE (:X);\n",
        },
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    bare_calls: list[list] = []

    def fake_bare(cmd, **k):
        bare_calls.append(cmd)
        # Fail the clear (the DETACH DELETE), succeed everything else.
        return 1 if any("DETACH DELETE" in a for a in cmd) else 0

    monkeypatch.setattr(restore, "_run_bare", fake_bare)

    rc = restore.run(str(archive))

    assert rc == 0
    joined = ["\n".join(c) for c in bare_calls]
    assert not any(
        "neo4j-restore.cypher" in s for s in joined
    ), "import must not run after a failed clear"
    assert any("Restore complete — NOT restored: Neo4j" in w for w in warns)


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


def test_ensure_running_noop_when_already_running(monkeypatch):
    """_ensure_running must not touch the network/compose at all when the
    container is already up -- only the "not running" path should act."""
    monkeypatch.setattr(restore.docker, "container_running", lambda s: True)
    calls: list[str] = []
    monkeypatch.setattr(
        restore.infra, "create_networks", lambda: calls.append("create_networks")
    )
    monkeypatch.setattr(restore.docker, "compose", lambda *a, **k: calls.append(a) or 0)

    restore._ensure_running("qdrant")

    assert calls == []


def test_ensure_running_brings_up_a_stopped_store(monkeypatch):
    """Found in a background audit: only postgres (#288) got this treatment --
    every other datastore's restore step silently found its container not
    running and gave up, which is the DEFAULT outcome of the documented
    stop-then-restore recovery procedure, not an edge case. _ensure_running
    generalizes the fix: recreate the network (idempotent) + compose up the
    service + wait for it to become healthy."""
    monkeypatch.setattr(restore.config, "DRY_RUN", False)
    monkeypatch.setattr(restore.docker, "container_running", lambda s: False)
    calls: list = []
    monkeypatch.setattr(
        restore.infra, "create_networks", lambda: calls.append("create_networks")
    )
    monkeypatch.setattr(restore.docker, "compose", lambda *a, **k: calls.append(a) or 0)
    monkeypatch.setattr(
        restore.docker, "wait_healthy", lambda s, **k: calls.append(("wait", s)) or True
    )

    restore._ensure_running("neo4j")

    assert calls == ["create_networks", ("up", "-d", "neo4j"), ("wait", "neo4j")]


def test_ensure_running_skips_health_wait_under_dry_run(monkeypatch):
    """DRY_RUN must preview (compose up echoed via docker.run's own seam) but
    never block on a real health wait -- mirrors the postgres block's own
    DRY_RUN gating."""
    monkeypatch.setattr(restore.config, "DRY_RUN", True)
    monkeypatch.setattr(restore.docker, "container_running", lambda s: False)
    monkeypatch.setattr(restore.infra, "create_networks", lambda: None)
    monkeypatch.setattr(restore.docker, "compose", lambda *a, **k: 0)

    def boom(*a, **k):
        raise AssertionError("wait_healthy must not run under DRY_RUN")

    monkeypatch.setattr(restore.docker, "wait_healthy", boom)

    restore._ensure_running("minio")  # must not raise


def test_safe_extractall_rejects_path_escaping_members(monkeypatch, tmp_path):
    """Found in a background audit: the pre-3.12 fallback (Python's `filter`
    kwarg needs >=3.12, missing on the Pi's actual 3.11.2) used to be a fully
    unfiltered extractall() -- a crafted member with a `../`-escaping path
    could write outside the destination directory entirely. The archive being
    restored is read from a caller-supplied path, not guaranteed to be an
    untampered backup.py artifact (the docs' own off-site rsync copy could be
    tampered with), so this must be rejected on every Python version, not
    just >=3.12."""
    real_extractall = tarfile.TarFile.extractall

    def fake_extractall(self, path=".", *args, **kwargs):
        if "filter" in kwargs:
            raise TypeError("extractall() got an unexpected keyword argument 'filter'")
        return real_extractall(self, path, *args, **kwargs)

    monkeypatch.setattr(tarfile.TarFile, "extractall", fake_extractall)

    dest = tmp_path / "dest"
    escape_target = tmp_path / "escaped.txt"
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo("../escaped.txt")
        data = b"pwned"
        info.size = len(data)
        import io

        tf.addfile(info, io.BytesIO(data))
        safe_info = tarfile.TarInfo("safe.txt")
        safe_info.size = 4
        tf.addfile(safe_info, io.BytesIO(b"safe"))

    with tarfile.open(archive, "r:gz") as tf:
        restore._safe_extractall(tf, dest)

    assert not escape_target.exists()
    assert (dest / "safe.txt").read_bytes() == b"safe"


def test_own_role_statement_filter_matches_only_bootstrap_role_lines():
    """#289: found live on hantal — pg_dumpall --clean's `DROP/CREATE/ALTER
    ROLE minder` can never succeed (minder is both the only role and the one
    the restore connects as), so ON_ERROR_STOP would hard-abort the restore
    before any real data is touched. Other roles/statements must survive.
    #644: this is now the per-line predicate applied while streaming."""
    keep = [
        b"-- Drop roles\n",
        b"DROP ROLE IF EXISTS readonly_reporter;\n",
        b"CREATE ROLE readonly_reporter;\n",
        b"DROP DATABASE IF EXISTS minder;\n",
        b"CREATE DATABASE minder;\n",
    ]
    strip = [
        b"DROP ROLE IF EXISTS minder;\n",
        b"CREATE ROLE minder;\n",
        b"ALTER ROLE minder WITH SUPERUSER LOGIN PASSWORD 'x';\n",
    ]
    for line in keep:
        assert restore._is_own_role_statement(line) is False, line
    for line in strip:
        assert restore._is_own_role_statement(line) is True, line


class _FakeStdin:
    def __init__(self):
        self.buf = bytearray()

    def write(self, b):
        self.buf.extend(b)

    def close(self):
        pass


class _FakeProc:
    """Captures what _restore_postgres streams to psql's stdin; `code` is the
    exit status returned from wait()."""

    def __init__(self, code=0):
        self.stdin = _FakeStdin()
        self._code = code

    def wait(self):
        return self._code


def test_postgres_restore_streams_filtered_dump_to_psql(monkeypatch, stubbed, tmp_path):
    """#289: `_restore_postgres` must feed the FILTERED dump to psql, not the
    raw file — otherwise ON_ERROR_STOP aborts on the bootstrap role's own
    always-failing DROP/CREATE/ALTER ROLE statements. #644: it now STREAMS the
    dump to psql's stdin via Popen (never a whole in-memory copy)."""
    archive = _make_archive(
        tmp_path,
        files={
            "postgres.sql": (
                "DROP ROLE IF EXISTS minder;\n"
                "CREATE ROLE minder;\n"
                "ALTER ROLE minder WITH SUPERUSER LOGIN PASSWORD 'x';\n"
                "DROP DATABASE IF EXISTS minder;\n"
                "CREATE DATABASE minder;\n"
            )
        },
    )
    warns, succs, errors = stubbed
    monkeypatch.setattr(restore.config, "ENV_FILE", tmp_path / "env")
    monkeypatch.setattr(restore, "_restore_postgres", _REAL_RESTORE_POSTGRES)
    proc = _FakeProc(code=0)
    monkeypatch.setattr(restore.subprocess, "Popen", lambda *a, **k: proc)

    rc = restore.run(str(archive))

    assert rc == 0
    out = bytes(proc.stdin.buf)
    # Bootstrap-role statements filtered out...
    assert b"DROP ROLE IF EXISTS minder;\n" not in out
    assert b"CREATE ROLE minder;\n" not in out
    assert b"ALTER ROLE minder WITH SUPERUSER LOGIN PASSWORD 'x';\n" not in out
    # ...real DB statements streamed through.
    assert b"DROP DATABASE IF EXISTS minder;\n" in out
    assert b"CREATE DATABASE minder;\n" in out


def test_restore_postgres_returns_false_on_nonzero_psql_exit(monkeypatch, tmp_path):
    """A psql failure (ON_ERROR_STOP) → non-zero wait() → False, so run()'s warn
    branch fires instead of a false success (#281)."""
    sql = tmp_path / "postgres.sql"
    sql.write_bytes(b"SELECT 1;\n")
    monkeypatch.setattr(restore.docker, "container_name", lambda s: "minder-postgres")
    monkeypatch.setattr(restore.subprocess, "Popen", lambda *a, **k: _FakeProc(code=1))
    assert restore._restore_postgres(sql) is False


def test_restore_postgres_missing_file_returns_false(monkeypatch, tmp_path):
    """An unreadable dump path returns False before psql is ever started."""
    started = []
    monkeypatch.setattr(
        restore.subprocess, "Popen", lambda *a, **k: started.append(1) or _FakeProc()
    )
    assert restore._restore_postgres(tmp_path / "does-not-exist.sql") is False
    assert started == []  # never launched psql
