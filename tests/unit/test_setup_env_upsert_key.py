"""Unit tests for scripts/setup/env.py's _upsert_env_key() locking (#374).

Found in a background audit: _upsert_env_key() (used by ensure_docker_gid(),
called right after fill_env_secrets() in prepare_env()) did a read-modify-write
of .env with no lock at all -- the exact same file fill_env_secrets() already
holds env.ENV_LOCK for. A concurrent setup.sh invocation racing this write
could silently discard whichever process wrote .env second.
"""

from contextlib import contextmanager

import pytest

from scripts.setup import env


@pytest.fixture
def _env_paths(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=1\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_LOCK", tmp_path / ".env.lock")
    return env_file


def test_replaces_existing_key(_env_paths):
    env._upsert_env_key("EXISTING", "2")
    assert _env_paths.read_text(encoding="utf-8") == "EXISTING=2\n"


def test_appends_missing_key(_env_paths):
    env._upsert_env_key("NEW_KEY", "value")
    lines = _env_paths.read_text(encoding="utf-8").splitlines()
    assert "NEW_KEY=value" in lines


def test_holds_the_shared_env_lock(_env_paths, monkeypatch):
    real_locked = env.filelock.locked
    calls = []

    @contextmanager
    def spy_locked(path):
        calls.append(path)
        with real_locked(path):
            yield

    monkeypatch.setattr(env.filelock, "locked", spy_locked)
    env._upsert_env_key("EXISTING", "3")
    assert calls == [env.ENV_LOCK]
