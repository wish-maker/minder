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

    assert (
        len(warned) == 1
    )  # app network (the dead minder-monitoring net, #650, is gone)
    assert not succeeded


def test_migrate_volume_names_aborts_on_failed_copy(monkeypatch, _quiet_log):
    """A failed data copy must raise, not log 'Migrated' — an operator trusting
    a false success could delete the old (only good) volume afterward."""
    monkeypatch.setattr(
        infra.docker,
        "volume_exists",
        lambda name: any(name.endswith(k) for k in infra._VOLUME_RENAMES),
    )
    monkeypatch.setattr(
        infra.docker, "run", lambda *a, **k: 1
    )  # create + copy both fail
    succeeded = []
    monkeypatch.setattr(infra.log, "success", lambda m: succeeded.append(m))
    errored = []
    monkeypatch.setattr(infra.log, "error", lambda m: errored.append(m))

    with pytest.raises(SystemExit):
        infra.migrate_volume_names()

    assert not any("Migrated" in m for m in succeeded)
    assert errored


def test_migrate_one_volume_removes_empty_partial_volume_after_failed_copy(
    monkeypatch, _quiet_log
):
    """Found in a background audit: on a failed copy, the just-created
    `new_name` volume (empty/partial) used to be left behind. On any later
    retry, `docker.volume_exists(new_name)` would then report True, so the
    function's own early-out ("nothing to migrate, or already migrated")
    would silently skip the migration forever -- `compose up` runs against
    that empty volume with no further error, operationally equivalent to
    data loss since the real data sits untouched in `old_name` but nothing
    ever uses it again."""
    existing = {"old"}  # old_name exists; new_name does not yet
    rm_calls = []

    def fake_volume_exists(name):
        return name in existing

    def fake_run(*cmd, **kwargs):
        argv = [str(c) for c in cmd]
        if argv[:3] == ["docker", "volume", "create"]:
            existing.add(argv[3])
            return 0
        if argv[:3] == ["docker", "volume", "rm"]:
            rm_calls.append(argv[3])
            existing.discard(argv[3])
            return 0
        # the alpine cp step -- force it to fail
        return 1

    monkeypatch.setattr(infra.docker, "volume_exists", fake_volume_exists)
    monkeypatch.setattr(infra.docker, "run", fake_run)

    result = infra._migrate_one_volume("old", "new", "old -> new")

    assert result is False
    assert rm_calls == ["new"]  # cleaned up so a retry can actually re-attempt
    assert "new" not in existing


def test_migrate_volume_names_reports_success_on_real_copy(monkeypatch, _quiet_log):
    monkeypatch.setattr(
        infra.docker,
        "volume_exists",
        lambda name: any(name.endswith(k) for k in infra._VOLUME_RENAMES),
    )
    monkeypatch.setattr(
        infra.docker, "run", lambda *a, **k: 0
    )  # create + copy both succeed
    succeeded = []
    monkeypatch.setattr(infra.log, "success", lambda m: succeeded.append(m))

    infra.migrate_volume_names()  # must not raise

    assert any("Migrated" in m for m in succeeded)


def test_bare_volume_renames_covers_openwebui_and_qdrant():
    """Regression guard (#408/#414): openwebui_data/qdrant_data were made
    `external: true` with a hardcoded name at first -- that fixed the Pi
    (which had them bare-named) but broke hantal (a second real deployment
    with no bare volume at all, only the standard "minder_<name>" one) with
    "external volume ... not found". The general fix is this migration
    entry, not a compose-level pin -- if it's ever removed, the same
    class of bug reappears for any host that still has the bare volume."""
    assert infra._BARE_VOLUME_RENAMES == {
        "openwebui_data": "openwebui_data",
        "qdrant_data": "qdrant_data",
    }


def test_migrate_volume_names_migrates_bare_legacy_volume(monkeypatch, _quiet_log):
    """A host with the Pi's bare "openwebui_data"/"qdrant_data" (no project
    prefix, unlike every other volume) and no "minder_<name>" counterpart yet
    must have it copied in -- exactly the scenario found live on the Pi."""
    monkeypatch.setattr(
        infra.docker,
        "volume_exists",
        lambda name: name in infra._BARE_VOLUME_RENAMES,  # only the bare names exist
    )
    monkeypatch.setattr(infra.docker, "run", lambda *a, **k: 0)
    succeeded = []
    monkeypatch.setattr(infra.log, "success", lambda m: succeeded.append(m))

    infra.migrate_volume_names()  # must not raise

    assert any("openwebui_data → minder_openwebui_data" in m for m in succeeded)
    assert any("qdrant_data → minder_qdrant_data" in m for m in succeeded)


def test_migrate_volume_names_noop_when_no_bare_legacy_volume(monkeypatch, _quiet_log):
    """A host that never had the bare-named volume (a fresh install, or
    hantal) must be a clean no-op -- Compose creates the standard-named
    volume itself, same as any other `driver: local` volume."""
    monkeypatch.setattr(infra.docker, "volume_exists", lambda name: False)
    run_calls = []
    monkeypatch.setattr(infra.docker, "run", lambda *a, **k: run_calls.append(a) or 0)

    infra.migrate_volume_names()  # must not raise

    assert run_calls == []
