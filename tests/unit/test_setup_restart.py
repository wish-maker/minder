"""Unit tests for the per-service `restart` validation (scripts/setup/restart.py).

The per-service form is python-only (#123 — bash cmd_restart is whole-stack only,
so the parity gate only covers the stop→start orchestration). This guards the
name-validation branch added on top: a mistyped/container-style name must fail
loudly *before* `docker compose restart` runs — including under --dry-run, where
the pre-fix code reported a false "✓ Restarted" for a nonexistent service.

No Docker: compose_services() and compose_all() are stubbed.
"""

import pytest

from scripts.setup import restart

SERVICES = ["redis", "postgres", "rag-pipeline", "ollama"]


@pytest.fixture
def rec_restart(monkeypatch):
    """Record docker.compose_all('restart', <svc>) calls; return rc 0."""
    calls: list[tuple] = []
    monkeypatch.setattr(restart.docker, "compose_all", lambda *a: calls.append(a) or 0)
    return calls


def test_unknown_service_rejected_before_compose(monkeypatch, rec_restart):
    monkeypatch.setattr(restart.docker, "compose_services", lambda: SERVICES)
    # container-style name (the real bug: `minder-redis` instead of `redis`)
    rc = restart.run("minder-redis")
    assert rc == 1
    assert rec_restart == []  # never reached compose


def test_valid_service_restarts(monkeypatch, rec_restart):
    monkeypatch.setattr(restart.docker, "compose_services", lambda: SERVICES)
    rc = restart.run("redis")
    assert rc == 0
    assert rec_restart == [("restart", "redis")]


def test_empty_service_list_skips_validation(monkeypatch, rec_restart):
    """docker/compose unqueryable → don't emit a false 'unknown service'; fall
    through so `docker compose restart` surfaces its own error."""
    monkeypatch.setattr(restart.docker, "compose_services", lambda: [])
    rc = restart.run("anything")
    assert rc == 0
    assert rec_restart == [("restart", "anything")]


def test_no_arg_is_whole_stack(monkeypatch):
    """Bare `restart` still means stop→start (never touches the service branch)."""
    order: list[str] = []
    monkeypatch.setattr(restart.stop, "run", lambda *a, **k: order.append("stop") or 0)
    monkeypatch.setattr(
        restart.start, "run", lambda *a, **k: order.append("start") or 0
    )
    monkeypatch.setattr(restart.time, "sleep", lambda *a, **k: None)
    restart.run()
    assert order == ["stop", "start"]
