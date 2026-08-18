"""Additional unit tests for scripts/setup/backup.py's remaining branches --
test_setup_backup.py already covers the #177 incomplete-summary regression
and the secret-permission fixes; this file covers everything else that was
still untested at 71%: _human_size's exabyte tier, _dump_to_file/_make_archive
tested directly (not just via the stubbed lambdas the other file uses), the
real env.backup copy path, every not-running warn branch, the remaining
failed-export branches (Neo4j/RabbitMQ), and the keep-last-7 prune. No
Docker: subprocess/docker are mocked.
"""

import sys
import tarfile

import pytest

from scripts.setup import backup

_posix_perms_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX file modes aren't representable on Windows/NTFS",
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
    warns, succs = [], []
    monkeypatch.setattr(backup.log, "warn", lambda m: warns.append(m))
    monkeypatch.setattr(backup.log, "success", lambda m: succs.append(m))
    for fn in ("section", "detail", "spinner_start", "spinner_stop"):
        monkeypatch.setattr(backup.log, fn, lambda *a, **k: None)
    return warns, succs


# ── _human_size ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "nbytes,expected",
    [
        (0, "0"),
        (1023, "1023"),
        (1024, "1.0K"),
        (1024**2, "1.0M"),
        (1024**5, "1.0P"),
        (1024**6, "1.0E"),
    ],
)
def test_human_size_units(nbytes, expected):
    assert backup._human_size(nbytes) == expected


# ── _du_sh ─────────────────────────────────────────────────────────────────────


def test_du_sh_returns_size_for_a_real_file(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"0" * 2048)
    assert backup._du_sh(f) == "2.0K"


def test_du_sh_returns_empty_for_a_missing_path(tmp_path):
    assert backup._du_sh(tmp_path / "does-not-exist") == ""


# ── _dump_to_file ──────────────────────────────────────────────────────────────


def test_dump_to_file_writes_stdout_and_returns_true_on_success(monkeypatch, tmp_path):
    def _fake_run(argv, stdout=None, stderr=None):
        stdout.write(b"dump contents")
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(backup.subprocess, "run", _fake_run)
    dest = tmp_path / "out.sql"

    assert backup._dump_to_file(["pg_dumpall"], dest) is True
    assert dest.read_bytes() == b"dump contents"


def test_dump_to_file_returns_false_on_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backup.subprocess,
        "run",
        lambda argv, stdout=None, stderr=None: type("R", (), {"returncode": 1})(),
    )
    dest = tmp_path / "out.sql"
    assert backup._dump_to_file(["pg_dumpall"], dest) is False


def test_dump_to_file_returns_false_on_oserror(monkeypatch, tmp_path):
    def _raise(argv, stdout=None, stderr=None):
        raise OSError("docker not found")

    monkeypatch.setattr(backup.subprocess, "run", _raise)
    dest = tmp_path / "out.sql"
    assert backup._dump_to_file(["pg_dumpall"], dest) is False


def test_dump_to_file_returns_false_when_dest_unwritable(tmp_path):
    dest = tmp_path / "no-such-dir" / "out.sql"
    assert backup._dump_to_file(["echo", "hi"], dest) is False


# ── _make_archive ──────────────────────────────────────────────────────────────


def test_make_archive_creates_a_real_tarball(tmp_path):
    base = tmp_path / "minder-20200101-000000"
    base.mkdir()
    (base / "env.backup").write_text("X=1\n")
    archive = tmp_path / "minder-20200101-000000.tar.gz"

    assert backup._make_archive(archive, tmp_path, base.name) is True
    assert archive.is_file()
    with tarfile.open(archive) as tf:
        assert f"{base.name}/env.backup" in tf.getnames()


def test_make_archive_returns_false_on_oserror(tmp_path):
    # base_dir/name doesn't exist -> tarfile.add raises FileNotFoundError (OSError).
    # tarfile.open("w:gz") creates the (empty) output file before add() ever
    # runs, so only the return value is asserted here, not file absence.
    archive = tmp_path / "out.tar.gz"
    assert backup._make_archive(archive, tmp_path, "does-not-exist") is False


# ── run(): the un-stubbed dest.chmod / env.backup real-copy path ─────────────


def test_dest_chmod_tolerates_oserror(monkeypatch, stubbed, tmp_path):
    warns, succs = stubbed
    monkeypatch.setattr(
        backup.Path, "chmod", lambda self, mode: (_ for _ in ()).throw(OSError("no"))
    )

    rc = backup.run()  # must not raise

    assert rc == 0


@_posix_perms_only
def test_env_backup_real_copy_and_chmod_600(monkeypatch, stubbed, tmp_path):
    warns, succs = stubbed
    env_file = tmp_path / "real.env"
    env_file.write_text("X=1\n")
    monkeypatch.setattr(backup.config, "ENV_FILE", env_file)
    # Keep the staging dir from being rmtree'd after a stubbed "successful"
    # compress, so env.backup survives for inspection below.
    monkeypatch.setattr(backup, "_make_archive", lambda *a, **k: False)

    backup.run()

    staging_dirs = [
        p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("minder-")
    ]
    env_backup = staging_dirs[0] / "env.backup"
    assert env_backup.read_text() == "X=1\n"
    assert (env_backup.stat().st_mode & 0o777) == 0o600
    assert ".env backed up" in succs


def test_env_backup_tolerates_chmod_oserror(monkeypatch, stubbed, tmp_path):
    warns, succs = stubbed
    env_file = tmp_path / "real.env"
    env_file.write_text("X=1\n")
    monkeypatch.setattr(backup.config, "ENV_FILE", env_file)
    monkeypatch.setattr(
        backup.Path, "chmod", lambda self, mode: (_ for _ in ()).throw(OSError("no"))
    )

    backup.run()  # must not raise

    assert ".env backed up" in succs


# ── not-running warn branches for every store ─────────────────────────────────


@pytest.mark.parametrize(
    "service,message",
    [
        ("postgres", "PostgreSQL not running — skipped"),
        ("neo4j", "Neo4j not running — skipped"),
        ("influxdb", "InfluxDB not running — skipped"),
        ("qdrant", "Qdrant not running — skipped"),
        ("minio", "MinIO not running — skipped"),
        ("rabbitmq", "RabbitMQ not running — skipped"),
    ],
)
def test_store_not_running_warns_and_is_not_in_skipped_summary(
    monkeypatch, stubbed, service, message
):
    """A not-running store is a deliberate, already-warned state -- distinct
    from the `skipped` list (which is only for a RUNNING store whose export
    failed) and must NOT additionally appear in the final NOT-captured line."""
    warns, succs = stubbed
    monkeypatch.setattr(backup.docker, "container_running", lambda s: s != service)

    rc = backup.run()

    assert rc == 0
    assert any(message in w for w in warns)
    assert not any("NOT captured" in w for w in warns)


# ── remaining failed-export branches ──────────────────────────────────────────


def test_neo4j_export_failure_is_loud(monkeypatch, stubbed):
    warns, succs = stubbed
    monkeypatch.setattr(backup.docker, "run", lambda *a, **k: 1)

    rc = backup.run()

    assert rc == 0
    assert any("Neo4j export failed" in w for w in warns)
    assert any("Backup complete — NOT captured: Neo4j" in w for w in warns)


def test_rabbitmq_export_failure_is_loud(monkeypatch, stubbed):
    warns, succs = stubbed

    def _run(*cmd, **k):
        return 1 if "rabbitmqctl" in cmd else 0

    monkeypatch.setattr(backup.docker, "run", _run)

    rc = backup.run()

    assert rc == 0
    assert any("RabbitMQ definitions export failed" in w for w in warns)
    assert any("Backup complete — NOT captured: RabbitMQ" in w for w in warns)


def test_qdrant_snapshot_failure_is_loud(monkeypatch, stubbed):
    warns, succs = stubbed

    def _run(*cmd, **k):
        return 1 if "/qdrant/storage" in cmd else 0

    monkeypatch.setattr(backup.docker, "run", _run)

    rc = backup.run()

    assert rc == 0
    assert any("Qdrant snapshot failed" in w for w in warns)
    assert any("Backup complete — NOT captured: Qdrant" in w for w in warns)


# ── prune (keep last 7) ────────────────────────────────────────────────────────


def test_prune_keeps_only_the_newest_seven_archives(monkeypatch, stubbed, tmp_path):
    warns, succs = stubbed
    # _make_archive is stubbed (no real archive written by this run itself),
    # so only these 9 pre-existing archives exist for the prune step to see.
    for i in range(9):
        (tmp_path / f"minder-2020010{i}-000000.tar.gz").write_bytes(b"x")

    backup.run()

    remaining = sorted(p.name for p in tmp_path.glob("minder-*.tar.gz"))
    assert len(remaining) == 7
    assert "minder-20200100-000000.tar.gz" not in remaining
    assert "minder-20200101-000000.tar.gz" not in remaining


def test_prune_noop_when_seven_or_fewer_archives(monkeypatch, stubbed, tmp_path):
    warns, succs = stubbed
    for i in range(3):
        (tmp_path / f"minder-2020010{i}-000000.tar.gz").write_bytes(b"x")

    backup.run()

    remaining = list(tmp_path.glob("minder-*.tar.gz"))
    assert len(remaining) == 3


def test_prune_tolerates_unlink_oserror(monkeypatch, stubbed, tmp_path):
    warns, succs = stubbed
    for i in range(9):
        (tmp_path / f"minder-2020010{i}-000000.tar.gz").write_bytes(b"x")
    monkeypatch.setattr(
        backup.Path, "unlink", lambda self: (_ for _ in ()).throw(OSError("busy"))
    )

    backup.run()  # must not raise
