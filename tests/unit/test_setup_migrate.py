"""Unit tests for migrate's postgres-down hard guard (migrate.py, #290).

#290: `migrate.run()`'s postgres-down guard used a plain `return 1` instead of
`raise SystemExit(1)` — install.py's `migrate.run("head")` call discards the
return value, so a failed migration phase inside `install` was silently
swallowed and the installer still reported success. No Docker: container
probes and the alembic-presence check are stubbed.
"""

import pytest

from scripts.setup import migrate


@pytest.fixture
def stubbed(monkeypatch):
    monkeypatch.setattr(migrate.log, "section", lambda *a, **k: None)
    monkeypatch.setattr(migrate.log, "detail", lambda *a, **k: None)
    monkeypatch.setattr(migrate.log, "info", lambda *a, **k: None)
    monkeypatch.setattr(migrate.log, "warn", lambda *a, **k: None)
    monkeypatch.setattr(migrate.log, "success", lambda *a, **k: None)
    errors: list[str] = []
    monkeypatch.setattr(migrate.log, "error", lambda m: errors.append(m))
    return errors


def test_postgres_not_running_raises_systemexit(monkeypatch, stubbed):
    """A plain `return 1` here is invisible to install.py's discarded-return-
    value call — only a raised SystemExit propagates far enough to actually
    abort an in-progress `install`, matching bash's `exit 1` under
    `set -euo pipefail`."""
    monkeypatch.setattr(migrate.docker, "container_running", lambda s: False)

    with pytest.raises(SystemExit) as exc_info:
        migrate.run("head")

    assert exc_info.value.code == 1
    assert any("PostgreSQL is not running" in e for e in stubbed)


def test_postgres_running_completes_normally(monkeypatch, stubbed):
    monkeypatch.setattr(migrate.docker, "container_running", lambda s: True)
    monkeypatch.setattr(migrate.docker, "container_name", lambda s: f"minder-{s}")
    monkeypatch.setattr(migrate, "_has_alembic", lambda cname: False)

    rc = migrate.run("head")

    assert rc == 0
    assert not stubbed
