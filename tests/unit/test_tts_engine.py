"""Unit tests for the TTS backend-selection/fallback logic (tts-stt/core/tts_engine.py, #272).

Piper (offline, default) with gTTS (online) fallback for languages without a
bundled Piper voice, or if piper-tts isn't installed. `synthesize()` is the
non-trivial multi-backend fallback chain flagged in #272 as having zero
regression coverage — these lock its branch selection.

Loaded by path: tts_engine.py does `from config import ...` (a bare config.py
name several sibling services also ship) -- force-load THIS service's config.py
under that name first, matching the established test_rag_ollama_failover_error.py
precedent for hyphenated-service modules that pull a same-named config/core.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "tts-stt"


def _load_tts_engine():
    config_spec = importlib.util.spec_from_file_location(
        "config", _SERVICE_DIR / "config.py"
    )
    config_mod = importlib.util.module_from_spec(config_spec)
    sys.modules["config"] = config_mod
    config_spec.loader.exec_module(config_mod)

    spec = importlib.util.spec_from_file_location(
        "tts_stt_tts_engine", _SERVICE_DIR / "core" / "tts_engine.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tts_stt_tts_engine"] = mod  # so unittest.mock.patch(...) can find it
    spec.loader.exec_module(mod)
    return mod


_mod = _load_tts_engine()


def test_piper_voice_path_none_for_unbundled_language(monkeypatch):
    monkeypatch.setattr(_mod, "PIPER_VOICES", {"en": "en_US-lessac-low"})
    assert _mod._piper_voice_path("de") is None


def test_piper_voice_path_none_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(_mod, "PIPER_VOICES", {"en": "en_US-lessac-low"})
    monkeypatch.setattr(_mod, "TTS_VOICES_DIR", str(tmp_path))
    assert _mod._piper_voice_path("en") is None


def test_piper_voice_path_found_when_file_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(_mod, "PIPER_VOICES", {"en": "en_US-lessac-low"})
    monkeypatch.setattr(_mod, "TTS_VOICES_DIR", str(tmp_path))
    (tmp_path / "en_US-lessac-low.onnx").write_bytes(b"fake-onnx")
    path = _mod._piper_voice_path("en")
    assert path == str(tmp_path / "en_US-lessac-low.onnx")


def test_synthesize_prefers_piper_when_voice_bundled(monkeypatch):
    monkeypatch.setattr(_mod, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", True)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)
    monkeypatch.setattr(
        _mod, "_synthesize_piper", lambda text, lang, slow: b"wav-bytes"
    )
    gtts_called = []
    monkeypatch.setattr(
        _mod, "_synthesize_gtts", lambda *a: gtts_called.append(a) or b"mp3-bytes"
    )

    data, media_type, ext = _mod.synthesize("merhaba", "tr", False)

    assert (data, media_type, ext) == (b"wav-bytes", "audio/wav", "wav")
    assert gtts_called == []  # gTTS never invoked -- Piper served it


def test_synthesize_falls_back_to_gtts_when_no_bundled_voice(monkeypatch):
    monkeypatch.setattr(_mod, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", True)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)
    # No bundled voice for this language -> Piper returns None (per its own contract)
    monkeypatch.setattr(_mod, "_synthesize_piper", lambda text, lang, slow: None)
    monkeypatch.setattr(_mod, "_synthesize_gtts", lambda text, lang, slow: b"mp3-bytes")

    data, media_type, ext = _mod.synthesize("hello", "de", False)

    assert (data, media_type, ext) == (b"mp3-bytes", "audio/mpeg", "mp3")


def test_synthesize_gtts_engine_setting_skips_piper_entirely(monkeypatch):
    monkeypatch.setattr(_mod, "TTS_ENGINE", "gtts")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", True)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)

    def _boom(*a):
        raise AssertionError("Piper must not be tried when TTS_ENGINE=gtts")

    monkeypatch.setattr(_mod, "_synthesize_piper", _boom)
    monkeypatch.setattr(_mod, "_synthesize_gtts", lambda text, lang, slow: b"mp3-bytes")

    data, media_type, ext = _mod.synthesize("hello", "en", False)
    assert (data, media_type, ext) == (b"mp3-bytes", "audio/mpeg", "mp3")


def test_synthesize_falls_back_to_gtts_when_piper_not_installed(monkeypatch):
    monkeypatch.setattr(_mod, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", False)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)
    monkeypatch.setattr(_mod, "_synthesize_gtts", lambda text, lang, slow: b"mp3-bytes")

    data, media_type, ext = _mod.synthesize("hello", "en", False)
    assert (data, media_type, ext) == (b"mp3-bytes", "audio/mpeg", "mp3")


def test_synthesize_raises_when_neither_engine_available(monkeypatch):
    monkeypatch.setattr(_mod, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", False)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", False)

    with pytest.raises(RuntimeError, match="No TTS engine available"):
        _mod.synthesize("hello", "en", False)


def test_load_piper_caches_per_language(monkeypatch):
    monkeypatch.setattr(_mod, "_piper_cache", {})
    monkeypatch.setattr(_mod, "_piper_voice_path", lambda lang: f"/voices/{lang}.onnx")
    fake_voice = MagicMock()
    fake_load = MagicMock(return_value=fake_voice)
    with patch.object(_mod, "PiperVoice", create=True) as piper_cls:
        piper_cls.load = fake_load
        first = _mod._load_piper("tr")
        second = _mod._load_piper("tr")
    assert first is fake_voice
    assert second is fake_voice
    fake_load.assert_called_once_with("/voices/tr.onnx")  # loaded once, cached after
