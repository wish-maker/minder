"""Unit tests for auxiliary database initialization (infra.py, #294) and the
unchecked-subprocess-failure fixes (#348).

#294: minder_authelia and minder_schemaregistry were missing from
EXTRA_DATABASES — both are hardcoded, non-configurable database names required
by services/authelia/configuration.yml and docker-compose.yml's schema-registry
datasource URLs, so on a fresh install both containers fatally crashed on
every startup ("database ... does not exist") and were restarted by Docker's
on-failure policy forever (confirmed live on the Pi: 835 and 363 restarts).

#348: create_networks/remove_networks/migrate_volume_names logged unconditional
success regardless of whether the underlying `docker.run(...)` call actually
succeeded — most seriously, a failed volume data-copy still reported
"Migrated", which could lead an operator to delete the only good copy of the
data (the old volume).

No Docker: subprocess.run/docker.run are stubbed.
"""

import pytest

from scripts.setup import config, infra


def test_extra_databases_includes_authelia_and_schema_registry():
    """Regression guard: these two names are hardcoded elsewhere (Authelia's
    own configuration.yml, schema-registry's JDBC URLs in docker-compose.yml)
    and are NOT configurable — if either is ever dropped from this tuple
    again, both services silently crash-loop forever on a fresh install."""
    assert "minder_authelia" in config.EXTRA_DATABASES
    assert "minder_schemaregistry" in config.EXTRA_DATABASES


def test_initialize_database_creates_every_extra_database(monkeypatch):
    monkeypatch.setattr(infra.docker, "compose", lambda *a, **k: 0)
    monkeypatch.setattr(infra.docker, "wait_postgres_ready", lambda *a, **k: True)
    monkeypatch.setattr(infra.docker, "container_name", lambda s: f"minder-{s}")
    for fn in ("step", "info", "detail"):
        monkeypatch.setattr(infra.log, fn, lambda *a, **k: None)

    calls: list[str] = []

    class _Result:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv[-1])
        return _Result()

    monkeypatch.setattr(infra.subprocess, "run", fake_run)

    infra.initialize_database()

    for db in config.EXTRA_DATABASES:
        assert any(f"CREATE DATABASE {db};" == c for c in calls)


@pytest.fixture
def _quiet_log(monkeypatch):
    for fn in ("step", "info", "detail", "success", "warn", "error"):
        monkeypatch.setattr(infra.log, fn, lambda *a, **k: None)


def test_create_networks_warns_not_success_on_failure(monkeypatch, _quiet_log):
    monkeypatch.setattr(infra.docker, "network_exists", lambda name: False)
    monkeypatch.setattr(infra.docker, "run", lambda *a, **k: 1)  # every create fails
    warned = []
    monkeypatch.setattr(infra.log, "warn", lambda m: warned.append(m))
    succeeded = []
    monkeypatch.setattr(infra.log, "success", lambda m: succeeded.append(m))

    infra.create_networks()  # must not raise

    assert len(warned) == 2  # app network + monitoring network
    assert not succeeded


def test_migrate_volume_names_aborts_on_failed_copy(monkeypatch, _quiet_log):
    """A failed data copy must raise, not log 'Migrated' — an operator trusting
    a false success could delete the old (only good) volume afterward."""
    monkeypatch.setattr(
        infra.docker,
        "volume_exists",
        lambda name: any(name.endswith(k) for k in infra._VOLUME_RENAMES),
    )
    monkeypatch.setattr(infra.docker, "run", lambda *a, **k: 1)  # create + copy both fail
    succeeded = []
    monkeypatch.setattr(infra.log, "success", lambda m: succeeded.append(m))
    errored = []
    monkeypatch.setattr(infra.log, "error", lambda m: errored.append(m))

    with pytest.raises(SystemExit):
        infra.migrate_volume_names()

    assert not any("Migrated" in m for m in succeeded)
    assert errored


def test_migrate_volume_names_reports_success_on_real_copy(monkeypatch, _quiet_log):
    monkeypatch.setattr(
        infra.docker,
        "volume_exists",
        lambda name: any(name.endswith(k) for k in infra._VOLUME_RENAMES),
    )
    monkeypatch.setattr(infra.docker, "run", lambda *a, **k: 0)  # create + copy both succeed
    succeeded = []
    monkeypatch.setattr(infra.log, "success", lambda m: succeeded.append(m))

    infra.migrate_volume_names()  # must not raise

    assert any("Migrated" in m for m in succeeded)
