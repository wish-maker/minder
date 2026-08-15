"""Unit tests for scripts/setup/env.py's fill_env_secrets() print-once
behavior for MINDER_AUTHELIA_ADMIN_PASSWORD (#473).

Every other SECRET_SPEC value is only ever read programmatically by a
service -- fill_env_secrets() never echoes their plaintext, by design
(log.detail("Generated secret for {key}") never includes the value). The
Authelia admin password is the one exception: a human has to type it back
in, so its plaintext must be printed to the terminal exactly once, the
moment it's generated, and never persisted to the on-disk setup log.

fill_env_secrets() itself has no other test coverage today -- this file
deliberately scopes to just the new behavior, not a full backfill of the
pre-existing function.
"""

import pytest

from scripts.setup import env


@pytest.fixture
def _env_paths(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_LOCK", tmp_path / ".env.lock")
    # Isolate to just the one key under test -- fill_env_secrets() would
    # otherwise also try to fill every other real SECRET_SPEC key.
    monkeypatch.setattr(env, "SECRET_SPEC", {"MINDER_AUTHELIA_ADMIN_PASSWORD": "32"})
    monkeypatch.setattr(env, "_live_core", lambda: None)  # no running stack to guard
    return env_file


def test_prints_the_plaintext_once_when_freshly_generated(_env_paths, capsys):
    env.fill_env_secrets()

    out = capsys.readouterr().out
    assert "Authelia Admin Password" in out
    assert "Username: admin" in out
    generated = env.get("MINDER_AUTHELIA_ADMIN_PASSWORD")
    assert generated
    assert f"Password: {generated}" in out


def test_stays_silent_on_a_later_run_once_already_set(_env_paths, capsys):
    _env_paths.write_text(
        "MINDER_AUTHELIA_ADMIN_PASSWORD=already-set-value\n", encoding="utf-8"
    )

    env.fill_env_secrets()

    out = capsys.readouterr().out
    assert "Authelia Admin Password" not in out
    assert env.get("MINDER_AUTHELIA_ADMIN_PASSWORD") == "already-set-value"
