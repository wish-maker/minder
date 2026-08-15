"""Unit tests for the `ollama-mode` verb, incl. the failover mode (#21).

Guards what the verb writes to .env for each mode — the single source of truth that
start_services reads to pick the compose profiles + consumer OLLAMA_BASE_URL:
  internal  → OLLAMA_BASE_URL empty, OLLAMA_FAILOVER_PRIMARY empty
  external  → OLLAMA_BASE_URL=<url>, OLLAMA_FAILOVER_PRIMARY empty
  failover  → OLLAMA_BASE_URL=router, OLLAMA_FAILOVER_PRIMARY=<host:port of the url>

Pure file edit: point both module-level ENV_FILE bindings at a temp .env.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from scripts.setup import env, ollama

_SEED = "OLLAMA_BASE_URL=\nOLLAMA_FAILOVER_PRIMARY=\nKEEP=1\n"


@pytest.fixture
def envfile(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text(_SEED, encoding="utf-8")
    # ollama.py and env.py each bind ENV_FILE at import → patch both.
    monkeypatch.setattr(ollama, "ENV_FILE", p)
    monkeypatch.setattr(env, "ENV_FILE", p)
    # ollama.run() locks env.ENV_LOCK (#374) -- keep it tmp-isolated too, same as
    # ENV_FILE, so tests never touch the real project's .env.lock.
    monkeypatch.setattr(env, "ENV_LOCK", tmp_path / ".env.lock")
    return p


def _vals(text):
    kv = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            kv[k] = v
    return kv


def test_failover_sets_router_url_and_primary_hostport(envfile):
    rc = ollama.run("failover", "http://192.168.68.104:11434")
    assert rc == 0
    kv = _vals(envfile.read_text(encoding="utf-8"))
    assert kv["OLLAMA_BASE_URL"] == "http://minder-ollama-router:11434"
    assert kv["OLLAMA_FAILOVER_PRIMARY"] == "192.168.68.104:11434"  # scheme stripped
    assert kv["KEEP"] == "1"  # unrelated lines untouched


def test_external_sets_url_and_clears_primary(envfile):
    # seed a stale failover primary, then switch to external — it must be cleared.
    envfile.write_text(
        "OLLAMA_BASE_URL=http://minder-ollama-router:11434\n"
        "OLLAMA_FAILOVER_PRIMARY=10.0.0.9:11434\n",
        encoding="utf-8",
    )
    rc = ollama.run("external", "http://192.168.68.104:11434")
    assert rc == 0
    kv = _vals(envfile.read_text(encoding="utf-8"))
    assert kv["OLLAMA_BASE_URL"] == "http://192.168.68.104:11434"
    assert kv["OLLAMA_FAILOVER_PRIMARY"] == ""  # cleared


def test_internal_clears_both(envfile):
    envfile.write_text(
        "OLLAMA_BASE_URL=http://minder-ollama-router:11434\n"
        "OLLAMA_FAILOVER_PRIMARY=10.0.0.9:11434\n",
        encoding="utf-8",
    )
    rc = ollama.run("internal")
    assert rc == 0
    kv = _vals(envfile.read_text(encoding="utf-8"))
    assert kv["OLLAMA_BASE_URL"] == ""
    assert kv["OLLAMA_FAILOVER_PRIMARY"] == ""


def test_failover_appends_primary_key_when_absent(envfile):
    envfile.write_text("OLLAMA_BASE_URL=\n", encoding="utf-8")  # no primary line yet
    rc = ollama.run("failover", "http://host.example:11434")
    assert rc == 0
    kv = _vals(envfile.read_text(encoding="utf-8"))
    assert kv["OLLAMA_FAILOVER_PRIMARY"] == "host.example:11434"


def test_invalid_url_rejected(envfile):
    assert ollama.run("failover", "not-a-url") == 1
    # .env untouched on rejection
    assert envfile.read_text(encoding="utf-8") == _SEED


def test_unknown_mode_usage_error(envfile):
    assert ollama.run("bogus") == 1


def test_run_holds_the_shared_env_lock(envfile, monkeypatch):
    """Regression guard: this used to read-modify-write .env with no lock at
    all, bypassing the advisory lock fill_env_secrets()/_upsert_env_key() hold
    for the exact same file (#374) -- a concurrent setup.sh invocation could
    silently discard whichever process wrote .env second."""
    from scripts.setup import filelock as filelock_mod

    calls = []
    real_locked = filelock_mod.locked

    @contextmanager
    def spy_locked(path):
        calls.append(path)
        with real_locked(path):
            yield

    monkeypatch.setattr(ollama, "filelock", SimpleNamespace(locked=spy_locked))
    assert ollama.run("internal") == 0
    assert calls == [env.ENV_LOCK]
