"""Unit tests for auxiliary database initialization (infra.py, #294).

#294: minder_authelia and minder_schemaregistry were missing from
EXTRA_DATABASES — both are hardcoded, non-configurable database names required
by services/authelia/configuration.yml and docker-compose.yml's schema-registry
datasource URLs, so on a fresh install both containers fatally crashed on
every startup ("database ... does not exist") and were restarted by Docker's
on-failure policy forever (confirmed live on the Pi: 835 and 363 restarts).

No Docker: subprocess.run is stubbed.
"""

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
