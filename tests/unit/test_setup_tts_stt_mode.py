"""Unit tests for the `tts-stt-mode` verb (mirrors ollama.py, #65 item 4).

Guards what the verb writes to .env for each mode -- the single source of truth
that start_services reads to pick the compose profiles + consumer TTS_STT_BASE_URL:
  internal  → TTS_STT_BASE_URL empty, TTS_STT_FAILOVER_PRIMARY empty
  external  → TTS_STT_BASE_URL=<url>, TTS_STT_FAILOVER_PRIMARY empty
  failover  → TTS_STT_BASE_URL=router, TTS_STT_FAILOVER_PRIMARY=<host:port of the url>

Had zero direct test coverage before this file (found in a background audit
alongside the missing .env write lock, fixed in the same change) -- ollama.py's
own test file (test_setup_ollama_mode.py) is the precedent this mirrors.

Pure file edit: point both module-level ENV_FILE bindings at a temp .env.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from scripts.setup import env, tts_stt

_SEED = "TTS_STT_BASE_URL=\nTTS_STT_FAILOVER_PRIMARY=\nKEEP=1\n"


@pytest.fixture
def envfile(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text(_SEED, encoding="utf-8")
    # tts_stt.py and env.py each bind ENV_FILE at import → patch both.
    monkeypatch.setattr(tts_stt, "ENV_FILE", p)
    monkeypatch.setattr(env, "ENV_FILE", p)
    # tts_stt.run() locks env.ENV_LOCK (#374) -- keep it tmp-isolated too.
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
    rc = tts_stt.run("failover", "http://192.168.68.104:8006")
    assert rc == 0
    kv = _vals(envfile.read_text(encoding="utf-8"))
    assert kv["TTS_STT_BASE_URL"] == "http://minder-tts-stt-router:8006"
    assert kv["TTS_STT_FAILOVER_PRIMARY"] == "192.168.68.104:8006"  # scheme stripped
    assert kv["KEEP"] == "1"  # unrelated lines untouched


def test_external_sets_url_and_clears_primary(envfile):
    envfile.write_text(
        "TTS_STT_BASE_URL=http://minder-tts-stt-router:8006\n"
        "TTS_STT_FAILOVER_PRIMARY=10.0.0.9:8006\n",
        encoding="utf-8",
    )
    rc = tts_stt.run("external", "http://192.168.68.104:8006")
    assert rc == 0
    kv = _vals(envfile.read_text(encoding="utf-8"))
    assert kv["TTS_STT_BASE_URL"] == "http://192.168.68.104:8006"
    assert kv["TTS_STT_FAILOVER_PRIMARY"] == ""  # cleared


def test_internal_clears_both(envfile):
    envfile.write_text(
        "TTS_STT_BASE_URL=http://minder-tts-stt-router:8006\n"
        "TTS_STT_FAILOVER_PRIMARY=10.0.0.9:8006\n",
        encoding="utf-8",
    )
    rc = tts_stt.run("internal")
    assert rc == 0
    kv = _vals(envfile.read_text(encoding="utf-8"))
    assert kv["TTS_STT_BASE_URL"] == ""
    assert kv["TTS_STT_FAILOVER_PRIMARY"] == ""


def test_invalid_url_rejected(envfile):
    assert tts_stt.run("failover", "not-a-url") == 1
    assert envfile.read_text(encoding="utf-8") == _SEED


def test_unknown_mode_usage_error(envfile):
    assert tts_stt.run("bogus") == 1


def test_run_holds_the_shared_env_lock(envfile, monkeypatch):
    """Regression guard: this used to read-modify-write .env with no lock at
    all, bypassing the advisory lock fill_env_secrets()/_upsert_env_key() hold
    for the exact same file (#374)."""
    from scripts.setup import filelock as filelock_mod

    calls = []
    real_locked = filelock_mod.locked

    @contextmanager
    def spy_locked(path):
        calls.append(path)
        with real_locked(path):
            yield

    monkeypatch.setattr(tts_stt, "filelock", SimpleNamespace(locked=spy_locked))
    assert tts_stt.run("internal") == 0
    assert calls == [env.ENV_LOCK]
