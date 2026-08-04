"""Unit test for install's migration-failure propagation (install.py, #290).

#290: install.py's `migrate.run("head")` call discarded the return value, so
when migrate.py's postgres-down guard used a plain `return 1`, a migration
failure mid-install was silently swallowed — health checks still ran and the
success banner still printed. migrate.py now raises SystemExit(1) instead;
this proves install.run() actually propagates it instead of continuing.
"""

import pytest

from scripts.setup import install


@pytest.fixture
def stubbed_up_to_migrate(monkeypatch):
    """No-op every install phase before migrate, and after it a marker that
    must NEVER be reached if migrate aborts."""
    monkeypatch.setattr(install, "_clear", lambda: None)
    monkeypatch.setattr(install.log, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(install.log, "_colors_on", lambda: False)
    monkeypatch.setattr(install.log, "progress_init", lambda *a, **k: None)
    monkeypatch.setattr(install.log, "progress_next", lambda *a, **k: None)
    monkeypatch.setattr(install.preflight, "check_prerequisites", lambda: None)
    monkeypatch.setattr(install.bundles, "seed_profile", lambda profile: True)
    monkeypatch.setattr(install.env, "prepare_env", lambda: None)
    monkeypatch.setattr(install.infra, "create_networks", lambda: None)
    monkeypatch.setattr(install.infra, "migrate_volume_names", lambda: None)
    monkeypatch.setattr(install.versions, "pull_all_images", lambda: None)
    monkeypatch.setattr(install.infra, "initialize_database", lambda: None)
    monkeypatch.setattr(install.infra, "initialize_minio", lambda: None)
    monkeypatch.setattr(install.lifecycle, "start_services", lambda: None)
    monkeypatch.setattr(install.lifecycle, "wait_for_services", lambda: None)
    monkeypatch.setattr(install.health, "download_ollama_models", lambda: None)

    reached_health_checks = []
    monkeypatch.setattr(
        install.health,
        "run_health_checks",
        lambda: reached_health_checks.append(True) or 0,
    )
    printed_banner = []
    monkeypatch.setattr(
        install.help_module,
        "print_success_banner",
        lambda: printed_banner.append(True),
    )
    return reached_health_checks, printed_banner


def test_migration_failure_aborts_install_before_success_banner(
    monkeypatch, stubbed_up_to_migrate
):
    reached_health_checks, printed_banner = stubbed_up_to_migrate

    def failing_migrate(target):
        raise SystemExit(1)

    monkeypatch.setattr(install.migrate, "run", failing_migrate)

    with pytest.raises(SystemExit) as exc_info:
        install.run("standard")

    assert exc_info.value.code == 1
    assert not reached_health_checks
    assert not printed_banner


def test_successful_migration_reaches_success_banner(
    monkeypatch, stubbed_up_to_migrate
):
    reached_health_checks, printed_banner = stubbed_up_to_migrate
    monkeypatch.setattr(install.migrate, "run", lambda target: 0)

    rc = install.run("standard")

    assert rc == 0
    assert reached_health_checks
    assert printed_banner
