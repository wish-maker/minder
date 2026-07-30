"""Unit tests for update._rebuild() output handling (scripts/setup/update.py).

Guards the two Windows crashes that killed the whole `update` verb mid-rebuild:
  1. `text=True` alone decodes docker/buildkit output with the platform default
     codec (cp1252 on Windows) → UnicodeDecodeError on stray progress bytes.
  2. `out.stdout + out.stderr` when one side is None → TypeError.

No Docker: subprocess.run is stubbed.
"""

import types

import pytest

from scripts.setup import update


@pytest.fixture(autouse=True)
def _not_dry_run(monkeypatch):
    monkeypatch.setattr(update.config, "DRY_RUN", False)


def _completed(stdout, stderr=""):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr)


def test_decodes_utf8_with_replace(monkeypatch):
    """subprocess.run must be invoked with utf-8 + errors='replace' so undecodable
    build output can never raise (cross-platform: the shim targets Windows too)."""
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs)
        return _completed("Step 1/5\nSuccessfully built abc123\nnoise\n")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    emitted = []
    monkeypatch.setattr(update.log, "_emit", lambda m: emitted.append(m))

    update._rebuild()

    assert seen.get("encoding") == "utf-8"
    assert seen.get("errors") == "replace"
    # only Step/Successfully/ERROR lines surface
    assert any("Step 1/5" in e for e in emitted)
    assert any("Successfully built" in e for e in emitted)
    assert not any("noise" in e for e in emitted)


def test_none_stdout_does_not_crash(monkeypatch):
    """stdout/stderr None must not blow up the concat (was TypeError on the crash
    path)."""
    monkeypatch.setattr(
        update.subprocess, "run", lambda *a, **k: _completed(None, None)
    )
    monkeypatch.setattr(update.log, "_emit", lambda m: None)
    update._rebuild()  # no exception = pass


def test_oserror_is_swallowed(monkeypatch):
    def boom(*a, **k):
        raise OSError("docker missing")

    monkeypatch.setattr(update.subprocess, "run", boom)
    update._rebuild()  # returns quietly


def test_dry_run_skips_build(monkeypatch):
    monkeypatch.setattr(update.config, "DRY_RUN", True)
    called = []
    monkeypatch.setattr(
        update.subprocess, "run", lambda *a, **k: called.append(1) or _completed("")
    )
    update._rebuild()
    assert called == []  # never shells out under --dry-run
