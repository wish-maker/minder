"""Unit tests for scripts/setup/infra.py -- create_networks, remove_networks,
_migrate_one_volume, migrate_volume_names, initialize_database, and
initialize_minio had zero direct unit tests (59%), only verified live/via the
dry-run gate. No real Docker: docker.*/subprocess.run are all mocked;
time.sleep is a no-op.
"""

import pytest

from scripts.setup import infra


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(infra.time, "sleep", lambda secs: None)


class _FakeCompleted:
    def __init__(self, returncode=0):
        self.returncode = returncode


# ── create_networks ────────────────────────────────────────────────────────────


def test_create_networks_skips_when_already_exists(monkeypatch):
    monkeypatch.setattr(infra.docker, "network_exists", lambda name: True)
    monkeypatch.setattr(
        infra.docker, "run", lambda *a: (_ for _ in ()).throw(AssertionError)
    )
    infra.create_networks()  # must not raise


def test_create_networks_success(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "network_exists", lambda name: False)
    monkeypatch.setattr(infra.docker, "run", lambda *a: 0)

    infra.create_networks()

    assert "created" in capfd.readouterr().out


def test_create_networks_warns_on_failure(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "network_exists", lambda name: False)
    monkeypatch.setattr(infra.docker, "run", lambda *a: 1)

    infra.create_networks()

    out = capfd.readouterr().out
    assert "was NOT created" in out


# ── remove_networks ────────────────────────────────────────────────────────────


def test_remove_networks_already_absent(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "network_exists", lambda name: False)

    infra.remove_networks()

    assert "already absent" in capfd.readouterr().out


def test_remove_networks_success(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "network_exists", lambda name: True)
    monkeypatch.setattr(infra.docker, "run", lambda *a: 0)

    infra.remove_networks()

    assert "removed" in capfd.readouterr().out


def test_remove_networks_warns_on_failure(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "network_exists", lambda name: True)
    monkeypatch.setattr(infra.docker, "run", lambda *a: 1)

    infra.remove_networks()

    assert "NOT removed" in capfd.readouterr().out


# ── _migrate_one_volume ──────────────────────────────────────────────────────


def test_migrate_one_volume_noop_when_old_absent(monkeypatch):
    monkeypatch.setattr(infra.docker, "volume_exists", lambda name: False)
    assert infra._migrate_one_volume("old", "new", "label") is None


def test_migrate_one_volume_noop_when_new_already_present(monkeypatch):
    monkeypatch.setattr(infra.docker, "volume_exists", lambda name: True)
    assert infra._migrate_one_volume("old", "new", "label") is None


def test_migrate_one_volume_success(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "volume_exists", lambda name: name == "old")
    monkeypatch.setattr(infra.docker, "run", lambda *a: 0)

    result = infra._migrate_one_volume("old", "new", "old -> new")

    assert result is True
    assert "Migrated: old -> new" in capfd.readouterr().out


def test_migrate_one_volume_create_fails(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "volume_exists", lambda name: name == "old")

    def _run(*args):
        return 1 if args[2] == "create" else 0

    monkeypatch.setattr(infra.docker, "run", _run)

    result = infra._migrate_one_volume("old", "new", "old -> new")

    out = capfd.readouterr().out
    assert result is False
    assert "Failed to migrate volume" in out
    assert "was NOT copied" in out


def test_migrate_one_volume_copy_fails_cleans_up_empty_volume(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "volume_exists", lambda name: name == "old")
    calls = []

    def _run(*args):
        calls.append(args)
        if args[2] == "create":
            return 0
        if args[1] == "run":
            return 1  # the copy itself fails
        if args[2] == "rm":
            return 0
        return 0

    monkeypatch.setattr(infra.docker, "run", _run)

    result = infra._migrate_one_volume("old", "new", "old -> new")

    assert result is False
    assert ("docker", "volume", "rm", "new") in calls


def test_migrate_one_volume_copy_fails_warns_when_cleanup_also_fails(
    monkeypatch, capfd
):
    monkeypatch.setattr(infra.docker, "volume_exists", lambda name: name == "old")

    def _run(*args):
        if args[2] == "create":
            return 0
        if args[1] == "run":
            return 1
        if args[2] == "rm":
            return 1  # cleanup itself also fails
        return 0

    monkeypatch.setattr(infra.docker, "run", _run)

    infra._migrate_one_volume("old", "new", "old -> new")

    out = capfd.readouterr().out
    assert "Could not remove the empty/partial volume" in out


# ── migrate_volume_names ───────────────────────────────────────────────────────


def test_migrate_volume_names_noop_when_nothing_to_migrate(monkeypatch, capfd):
    monkeypatch.setattr(infra, "_migrate_one_volume", lambda old, new, label: None)

    infra.migrate_volume_names()

    assert "No volume migrations needed" in capfd.readouterr().out


def test_migrate_volume_names_reports_when_something_migrated(monkeypatch, capfd):
    calls = {"n": 0}

    def _fake(old, new, label):
        calls["n"] += 1
        return True if calls["n"] == 1 else None

    monkeypatch.setattr(infra, "_migrate_one_volume", _fake)

    infra.migrate_volume_names()

    out = capfd.readouterr().out
    assert "left in place" in out


def test_migrate_volume_names_reports_when_a_bare_volume_migrated(monkeypatch, capfd):
    def _fake(old, new, label):
        return True if old in infra._BARE_VOLUME_RENAMES else None

    monkeypatch.setattr(infra, "_migrate_one_volume", _fake)

    infra.migrate_volume_names()

    assert "left in place" in capfd.readouterr().out


def test_migrate_volume_names_exits_1_when_any_migration_failed(monkeypatch):
    monkeypatch.setattr(infra, "_migrate_one_volume", lambda old, new, label: False)

    with pytest.raises(SystemExit) as exc:
        infra.migrate_volume_names()

    assert exc.value.code == 1


def test_migrate_volume_names_uses_container_prefix_for_prefixed_renames(monkeypatch):
    seen = []
    monkeypatch.setattr(
        infra,
        "_migrate_one_volume",
        lambda old, new, label: seen.append((old, new)) or None,
    )

    infra.migrate_volume_names()

    prefix = infra.config.CONTAINER_PREFIX
    assert (
        f"{prefix}_docker_traefik_letsencrypt",
        f"{prefix}_traefik_letsencrypt",
    ) in seen
    # bare-volume renames: OLD name has no prefix at all.
    assert ("openwebui_data", f"{prefix}_openwebui_data") in seen


# ── initialize_database ────────────────────────────────────────────────────────


def test_initialize_database_exits_when_postgres_never_ready(monkeypatch):
    monkeypatch.setattr(infra.docker, "compose", lambda *a: 0)
    monkeypatch.setattr(infra.docker, "wait_postgres_ready", lambda: False)

    with pytest.raises(SystemExit):
        infra.initialize_database()


def test_initialize_database_creates_each_extra_database(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "compose", lambda *a: 0)
    monkeypatch.setattr(infra.docker, "wait_postgres_ready", lambda: True)
    monkeypatch.setattr(infra.config, "EXTRA_DATABASES", ("news_db", "crypto_db"))
    monkeypatch.setattr(infra.docker, "container_name", lambda svc: "minder-postgres")

    def _run(argv, **kw):
        if "CREATE DATABASE news_db;" in argv:
            return _FakeCompleted(returncode=0)
        if "CREATE DATABASE crypto_db;" in argv:
            return _FakeCompleted(returncode=1)
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(infra.subprocess, "run", _run)

    infra.initialize_database()

    out = capfd.readouterr().out
    assert "Created: news_db" in out
    assert "Already exists: crypto_db" in out
    assert "Database initialisation complete" in out


def test_initialize_database_reports_timezone_set_success(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "compose", lambda *a: 0)
    monkeypatch.setattr(infra.docker, "wait_postgres_ready", lambda: True)
    monkeypatch.setattr(infra.config, "EXTRA_DATABASES", ())
    monkeypatch.setattr(infra.docker, "container_name", lambda svc: "minder-postgres")
    monkeypatch.setattr(
        infra.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=0)
    )

    infra.initialize_database()

    assert "Database timezone set to UTC" in capfd.readouterr().out


def test_initialize_database_reports_timezone_set_failure(monkeypatch, capfd):
    monkeypatch.setattr(infra.docker, "compose", lambda *a: 0)
    monkeypatch.setattr(infra.docker, "wait_postgres_ready", lambda: True)
    monkeypatch.setattr(infra.config, "EXTRA_DATABASES", ())
    monkeypatch.setattr(infra.docker, "container_name", lambda svc: "minder-postgres")
    monkeypatch.setattr(
        infra.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=1)
    )

    infra.initialize_database()

    assert "Could not set database timezone to UTC" in capfd.readouterr().out


# ── initialize_minio ───────────────────────────────────────────────────────────


def test_initialize_minio_skips_when_not_in_compose(monkeypatch, tmp_path, capfd):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  postgres:\n    image: postgres\n")
    monkeypatch.setattr(infra.config, "COMPOSE_FILE", compose_file)
    monkeypatch.setattr(
        infra.docker, "compose", lambda *a: (_ for _ in ()).throw(AssertionError)
    )

    infra.initialize_minio()

    assert "MinIO service not defined" in capfd.readouterr().out


def test_initialize_minio_tolerates_compose_file_read_oserror(
    monkeypatch, tmp_path, capfd
):
    monkeypatch.setattr(infra.config, "COMPOSE_FILE", tmp_path / "missing.yml")
    monkeypatch.setattr(
        infra.docker, "compose", lambda *a: (_ for _ in ()).throw(AssertionError)
    )

    infra.initialize_minio()  # must not raise

    assert "MinIO service not defined" in capfd.readouterr().out


def test_initialize_minio_exits_when_never_healthy(monkeypatch, tmp_path):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  minio:\n    image: minio\n")
    monkeypatch.setattr(infra.config, "COMPOSE_FILE", compose_file)
    monkeypatch.setattr(infra.docker, "compose", lambda *a: 0)
    monkeypatch.setattr(infra.docker, "wait_healthy", lambda svc, timeout: False)

    with pytest.raises(SystemExit):
        infra.initialize_minio()


@pytest.fixture
def _minio_ready(monkeypatch, tmp_path):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  minio:\n    image: minio\n")
    monkeypatch.setattr(infra.config, "COMPOSE_FILE", compose_file)
    monkeypatch.setattr(infra.docker, "compose", lambda *a: 0)
    monkeypatch.setattr(infra.docker, "wait_healthy", lambda svc, timeout: True)
    monkeypatch.setattr(infra.docker, "container_name", lambda svc: "minder-minio")
    monkeypatch.setattr(infra.env, "get", lambda key: "")


def test_initialize_minio_warns_when_alias_fails(monkeypatch, _minio_ready, capfd):
    monkeypatch.setattr(
        infra.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=1)
    )

    infra.initialize_minio()

    assert "Could not configure mc 'mydata' alias" in capfd.readouterr().out


def test_initialize_minio_creates_buckets_and_sets_public_policy(
    monkeypatch, _minio_ready, capfd
):
    def _run(argv, **kw):
        if "alias" in argv:
            return _FakeCompleted(returncode=0)
        if "ls" in argv:
            return _FakeCompleted(returncode=1)  # doesn't exist yet
        if "mb" in argv:
            return _FakeCompleted(returncode=0)
        if "anonymous" in argv:
            return _FakeCompleted(returncode=0)
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(infra.subprocess, "run", _run)

    infra.initialize_minio()

    out = capfd.readouterr().out
    assert "Created: rag-documents" in out
    assert "Set public policy: rag-documents" in out
    assert "Created: model-checkpoints" in out
    assert "Set public policy: model-checkpoints" not in out
    assert "MinIO initialisation complete" in out


def test_initialize_minio_skips_existing_buckets(monkeypatch, _minio_ready, capfd):
    def _run(argv, **kw):
        if "alias" in argv:
            return _FakeCompleted(returncode=0)
        if "ls" in argv:
            return _FakeCompleted(returncode=0)  # already exists
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(infra.subprocess, "run", _run)

    infra.initialize_minio()

    out = capfd.readouterr().out
    assert "Already exists: rag-documents" in out
    assert "Created:" not in out


def test_initialize_minio_warns_on_bucket_creation_failure(
    monkeypatch, _minio_ready, capfd
):
    def _run(argv, **kw):
        if "alias" in argv:
            return _FakeCompleted(returncode=0)
        if "ls" in argv:
            return _FakeCompleted(returncode=1)
        if "mb" in argv:
            return _FakeCompleted(returncode=1)
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(infra.subprocess, "run", _run)

    infra.initialize_minio()

    assert "Failed to create bucket: rag-documents" in capfd.readouterr().out
