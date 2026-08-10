"""Unit tests for update._rebuild() output handling (scripts/setup/update.py).

Guards the two Windows crashes that killed the whole `update` verb mid-rebuild:
  1. `text=True` alone decodes docker/buildkit output with the platform default
     codec (cp1252 on Windows) → UnicodeDecodeError on stray progress bytes.
  2. `out.stdout + out.stderr` when one side is None → TypeError.

Also guards #346: a failed build must make `_rebuild()` return False and
`run()` abort before the rolling restart, instead of silently continuing with
whatever images were already local.

No Docker: subprocess.run is stubbed.
"""

import types

import pytest

from scripts.setup import update


@pytest.fixture(autouse=True)
def _not_dry_run(monkeypatch):
    monkeypatch.setattr(update.config, "DRY_RUN", False)


def _completed(stdout, stderr="", returncode=0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_rebuild_activates_profile_gated_services(monkeypatch):
    """Without an explicit service argument, `docker compose build` only
    considers services in the ACTIVE profile set -- tts-stt is
    profiles: ["internal-tts-stt"] (the one profile-gated service with its
    own build: context), so a bare `build` silently skipped it on every
    `update`, leaving it stuck on a stale image. Confirmed live: 4 days
    stale despite several successful-looking `update` runs. Must activate
    the same profile set compose_services()/compose_all() already use."""
    seen_argv = []

    def fake_run(argv, **kwargs):
        seen_argv.extend(argv)
        return _completed("Successfully built abc123\n")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    monkeypatch.setattr(update.log, "_emit", lambda m: None)

    assert update._rebuild() is True
    for profile in (
        "monitoring",
        "internal-ollama",
        "ollama-router",
        "internal-tts-stt",
        "tts-stt-router",
    ):
        assert profile in seen_argv, f"missing --profile {profile}"
    assert "build" in seen_argv


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

    ok = update._rebuild()

    assert ok is True
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
    assert update._rebuild() is True  # no exception, returncode 0 → success


def test_oserror_returns_false(monkeypatch):
    def boom(*a, **k):
        raise OSError("docker missing")

    monkeypatch.setattr(update.subprocess, "run", boom)
    assert update._rebuild() is False


def test_dry_run_skips_build(monkeypatch):
    monkeypatch.setattr(update.config, "DRY_RUN", True)
    called = []
    monkeypatch.setattr(
        update.subprocess, "run", lambda *a, **k: called.append(1) or _completed("")
    )
    assert update._rebuild() is True
    assert called == []  # never shells out under --dry-run


def test_nonzero_returncode_is_a_failure(monkeypatch):
    """#346: a build that exits non-zero (e.g. a broken credential helper) must
    be reported as a failure, not treated like a no-op success."""
    monkeypatch.setattr(
        update.subprocess,
        "run",
        lambda *a, **k: _completed("", "error getting credentials", returncode=1),
    )
    monkeypatch.setattr(update.log, "_emit", lambda m: None)
    logged_errors = []
    monkeypatch.setattr(update.log, "error", lambda m: logged_errors.append(m))

    assert update._rebuild() is False
    assert logged_errors  # a clear error was surfaced, not swallowed


def test_rolling_restart_includes_client(monkeypatch):
    """The client SPA's image gets rebuilt by `docker compose build` (it's a
    regular service in the compose file) but was never in the rolling-restart
    loop -- so a rebuilt client image never actually reached the running
    container until something else (a full stop/start) recreated it. Confirmed
    live on hantal: the served bundle was a stale, smaller build than the repo's
    current HEAD despite `update` reporting success repeatedly."""
    monkeypatch.setattr(update.versions, "pull_all_images", lambda: None)
    monkeypatch.setattr(update, "_rebuild", lambda: True)
    monkeypatch.setattr(update.time, "sleep", lambda *a: None)
    monkeypatch.setattr(update.docker, "container_running", lambda svc: True)
    restarted = []
    monkeypatch.setattr(
        update.docker,
        "compose",
        lambda *args: restarted.append(args[-1]) if args and args[-1] else None,
    )

    rc = update.run()

    assert rc == 0
    assert "client" in restarted


def test_run_aborts_before_rolling_restart_on_rebuild_failure(monkeypatch):
    """#346: run() must not reach 'Performing rolling restart' (and print
    'Update complete') when the rebuild failed."""
    monkeypatch.setattr(update.versions, "pull_all_images", lambda: None)
    monkeypatch.setattr(update, "_rebuild", lambda: False)
    restarted = []
    monkeypatch.setattr(
        update.docker, "container_running", lambda svc: restarted.append(svc) or True
    )

    rc = update.run()

    assert rc != 0
    assert restarted == []  # never even checked which services to restart
