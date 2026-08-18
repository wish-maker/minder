"""Additional unit tests for scripts/setup/migrate.py's remaining branches --
test_setup_migrate.py already covers the #290/#348 SystemExit-not-return
regression guards. This file covers _has_alembic directly, the per-service
not-running skip, and the successful-migration-applied branch. No Docker:
subprocess/docker are mocked.
"""

from scripts.setup import migrate

# ── _has_alembic ───────────────────────────────────────────────────────────────


def test_has_alembic_true_on_zero_returncode(monkeypatch):
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda argv, **kw: type("R", (), {"returncode": 0})(),
    )
    assert migrate._has_alembic("minder-api-gateway") is True


def test_has_alembic_false_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(
        migrate.subprocess,
        "run",
        lambda argv, **kw: type("R", (), {"returncode": 1})(),
    )
    assert migrate._has_alembic("minder-api-gateway") is False


def test_has_alembic_false_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("docker not found")

    monkeypatch.setattr(migrate.subprocess, "run", _raise)
    assert migrate._has_alembic("minder-api-gateway") is False


# ── run(): per-service not-running skip + successful-migration branch ────────


def _quiet(monkeypatch):
    for fn in ("section", "detail", "info", "warn", "success"):
        monkeypatch.setattr(migrate.log, fn, lambda *a, **k: None)


def test_run_skips_a_service_that_is_not_running(monkeypatch, capfd):
    _quiet(monkeypatch)
    monkeypatch.setattr(migrate.docker, "container_running", lambda s: s == "postgres")
    details = []
    monkeypatch.setattr(migrate.log, "detail", lambda m: details.append(m))
    monkeypatch.setattr(
        migrate, "_has_alembic", lambda cname: (_ for _ in ()).throw(AssertionError)
    )

    rc = migrate.run("head")

    assert rc == 0
    assert any("api-gateway — not running, skipping" in d for d in details)


def test_run_reports_success_for_an_applied_migration(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(migrate.docker, "container_running", lambda s: True)
    monkeypatch.setattr(migrate.docker, "container_name", lambda s: f"minder-{s}")
    monkeypatch.setattr(migrate, "_has_alembic", lambda cname: True)
    calls = []
    monkeypatch.setattr(
        migrate.docker, "run", lambda *args, **kw: calls.append(args) or 0
    )
    succs = []
    monkeypatch.setattr(migrate.log, "success", lambda m: succs.append(m))

    rc = migrate.run("head")

    assert rc == 0
    assert any("api-gateway — migrations applied" in s for s in succs)
    assert (
        "docker",
        "exec",
        "minder-api-gateway",
        "alembic",
        "upgrade",
        "head",
    ) in calls


def test_run_reports_no_alembic_skip_message(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(migrate.docker, "container_running", lambda s: True)
    monkeypatch.setattr(migrate.docker, "container_name", lambda s: f"minder-{s}")
    monkeypatch.setattr(migrate, "_has_alembic", lambda cname: False)
    details = []
    monkeypatch.setattr(migrate.log, "detail", lambda m: details.append(m))

    rc = migrate.run("head")

    assert rc == 0
    assert any("schema self-initialized on startup" in d for d in details)
