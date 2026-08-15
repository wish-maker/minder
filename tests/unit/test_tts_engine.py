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
    monkeypatch.setattr(
        _mod, "PIPER_VOICES", {"en": {"default": {"model": "en_US-lessac-low"}}}
    )
    assert _mod._piper_voice_path("de", None) is None


def test_piper_voice_path_none_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        _mod, "PIPER_VOICES", {"en": {"default": {"model": "en_US-lessac-low"}}}
    )
    monkeypatch.setattr(_mod.settings, "TTS_VOICES_DIR", str(tmp_path))
    assert _mod._piper_voice_path("en", None) is None


def test_piper_voice_path_found_when_file_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(
        _mod, "PIPER_VOICES", {"en": {"default": {"model": "en_US-lessac-low"}}}
    )
    monkeypatch.setattr(_mod.settings, "TTS_VOICES_DIR", str(tmp_path))
    (tmp_path / "en_US-lessac-low.onnx").write_bytes(b"fake-onnx")
    path = _mod._piper_voice_path("en", None)
    assert path == str(tmp_path / "en_US-lessac-low.onnx")


def test_piper_voice_path_selects_requested_voice(monkeypatch, tmp_path):
    monkeypatch.setattr(
        _mod,
        "PIPER_VOICES",
        {
            "en": {
                "default": {"model": "en_US-lessac-low"},
                "female": {"model": "en_US-hfc_female-medium"},
            }
        },
    )
    monkeypatch.setattr(_mod.settings, "TTS_VOICES_DIR", str(tmp_path))
    (tmp_path / "en_US-hfc_female-medium.onnx").write_bytes(b"fake-onnx")
    assert _mod._piper_voice_path("en", "female") == str(
        tmp_path / "en_US-hfc_female-medium.onnx"
    )


def test_resolve_voice_id_falls_back_to_default_for_unknown_voice(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "PIPER_VOICES",
        {"en": {"default": {"model": "en_US-lessac-low"}, "male": {"model": "m"}}},
    )
    assert _mod._resolve_voice_id("en", "nonexistent-voice") == "default"
    assert _mod._resolve_voice_id("en", None) == "default"
    assert _mod._resolve_voice_id("en", "male") == "male"


def test_list_voices_only_includes_onnx_present_on_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(
        _mod,
        "PIPER_VOICES",
        {
            "en": {
                "default": {"model": "en_US-lessac-low", "label": "Default"},
                "female": {"model": "en_US-hfc_female-medium", "label": "Female"},
            }
        },
    )
    monkeypatch.setattr(_mod.settings, "TTS_VOICES_DIR", str(tmp_path))
    (tmp_path / "en_US-lessac-low.onnx").write_bytes(b"fake-onnx")
    # "female"'s .onnx is NOT written -- must not be offered as a real choice.
    assert _mod.list_voices("en") == [{"id": "default", "label": "Default"}]


def test_list_voices_empty_for_gtts_only_language(monkeypatch):
    monkeypatch.setattr(
        _mod, "PIPER_VOICES", {"en": {"default": {"model": "en_US-lessac-low"}}}
    )
    assert _mod.list_voices("de") == []


def test_synthesize_prefers_piper_when_voice_bundled(monkeypatch):
    monkeypatch.setattr(_mod.settings, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", True)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)
    monkeypatch.setattr(
        _mod, "_synthesize_piper", lambda text, lang, slow, voice: b"wav-bytes"
    )
    gtts_called = []
    monkeypatch.setattr(
        _mod, "_synthesize_gtts", lambda *a: gtts_called.append(a) or b"mp3-bytes"
    )

    data, media_type, ext = _mod.synthesize("merhaba", "tr", False)

    assert (data, media_type, ext) == (b"wav-bytes", "audio/wav", "wav")
    assert gtts_called == []  # gTTS never invoked -- Piper served it


def test_synthesize_passes_voice_through_to_piper(monkeypatch):
    monkeypatch.setattr(_mod.settings, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", True)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)
    seen = []
    monkeypatch.setattr(
        _mod,
        "_synthesize_piper",
        lambda text, lang, slow, voice: seen.append(voice) or b"wav-bytes",
    )

    _mod.synthesize("hello", "en", False, voice="male")

    assert seen == ["male"]


def test_synthesize_falls_back_to_gtts_when_no_bundled_voice(monkeypatch):
    monkeypatch.setattr(_mod.settings, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", True)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)
    # No bundled voice for this language -> Piper returns None (per its own contract)
    monkeypatch.setattr(_mod, "_synthesize_piper", lambda text, lang, slow, voice: None)
    monkeypatch.setattr(_mod, "_synthesize_gtts", lambda text, lang, slow: b"mp3-bytes")

    data, media_type, ext = _mod.synthesize("hello", "de", False)

    assert (data, media_type, ext) == (b"mp3-bytes", "audio/mpeg", "mp3")


def test_synthesize_gtts_engine_setting_skips_piper_entirely(monkeypatch):
    monkeypatch.setattr(_mod.settings, "TTS_ENGINE", "gtts")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", True)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)

    def _boom(*a):
        raise AssertionError("Piper must not be tried when TTS_ENGINE=gtts")

    monkeypatch.setattr(_mod, "_synthesize_piper", _boom)
    monkeypatch.setattr(_mod, "_synthesize_gtts", lambda text, lang, slow: b"mp3-bytes")

    data, media_type, ext = _mod.synthesize("hello", "en", False)
    assert (data, media_type, ext) == (b"mp3-bytes", "audio/mpeg", "mp3")


def test_synthesize_falls_back_to_gtts_when_piper_not_installed(monkeypatch):
    monkeypatch.setattr(_mod.settings, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", False)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", True)
    monkeypatch.setattr(_mod, "_synthesize_gtts", lambda text, lang, slow: b"mp3-bytes")

    data, media_type, ext = _mod.synthesize("hello", "en", False)
    assert (data, media_type, ext) == (b"mp3-bytes", "audio/mpeg", "mp3")


def test_synthesize_raises_when_neither_engine_available(monkeypatch):
    monkeypatch.setattr(_mod.settings, "TTS_ENGINE", "piper")
    monkeypatch.setattr(_mod, "PIPER_AVAILABLE", False)
    monkeypatch.setattr(_mod, "GTTS_AVAILABLE", False)

    with pytest.raises(RuntimeError, match="No TTS engine available"):
        _mod.synthesize("hello", "en", False)


def test_load_piper_caches_per_language(monkeypatch):
    monkeypatch.setattr(_mod, "_piper_cache", {})
    monkeypatch.setattr(_mod, "_resolve_voice_id", lambda lang, voice: "default")
    monkeypatch.setattr(
        _mod, "_piper_voice_path", lambda lang, voice: f"/voices/{lang}.onnx"
    )
    fake_voice = MagicMock()
    fake_load = MagicMock(return_value=fake_voice)
    with patch.object(_mod, "PiperVoice", create=True) as piper_cls:
        piper_cls.load = fake_load
        first = _mod._load_piper("tr", None)
        second = _mod._load_piper("tr", None)
    assert first is fake_voice
    assert second is fake_voice
    fake_load.assert_called_once_with("/voices/tr.onnx")  # loaded once, cached after


def test_load_piper_caches_separately_per_voice(monkeypatch):
    """A different voice for the SAME language must not hit the other voice's
    cache entry -- each (language, voice) pair loads its own ONNX model."""
    monkeypatch.setattr(_mod, "_piper_cache", {})
    monkeypatch.setattr(_mod, "_resolve_voice_id", lambda lang, voice: voice)
    monkeypatch.setattr(
        _mod, "_piper_voice_path", lambda lang, voice: f"/voices/{lang}-{voice}.onnx"
    )
    fake_load = MagicMock(side_effect=lambda path: MagicMock(name=path))
    with patch.object(_mod, "PiperVoice", create=True) as piper_cls:
        piper_cls.load = fake_load
        male = _mod._load_piper("en", "male")
        female = _mod._load_piper("en", "female")
    assert male is not female
    assert fake_load.call_count == 2


def test_synthesize_gtts_cleans_up_temp_file_even_when_save_fails(
    monkeypatch, tmp_path
):
    """Regression guard: tts.save() is a network call to Google Translate that
    can raise (DNS failure, rate-limiting, any outage) -- the temp file is
    created (delete=False) BEFORE that call, so cleanup must be in a
    try/finally around the whole lifecycle, not just the read. It used to
    only wrap the read, leaking one file into /tmp per failed gTTS call."""
    created_path = {}

    class _FakeTempFile:
        def __init__(self, path):
            self.name = path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_named_temp_file(delete, suffix):
        path = str(tmp_path / f"fake{suffix}")
        # Simulate NamedTemporaryFile actually creating the file on disk.
        open(path, "wb").close()
        created_path["path"] = path
        return _FakeTempFile(path)

    monkeypatch.setattr(_mod.tempfile, "NamedTemporaryFile", fake_named_temp_file)

    class _FakeGTTSRaises:
        def __init__(self, **kwargs):
            pass

        def save(self, path):
            raise RuntimeError("Google Translate unreachable")

    # gtts isn't installed in every environment this test suite runs in
    # (GTTS_AVAILABLE gates real use, same pattern as OLLAMA_AVAILABLE
    # elsewhere) -- raising=False allows setting an attribute that may not
    # exist on the module yet.
    monkeypatch.setattr(_mod, "gTTS", _FakeGTTSRaises, raising=False)

    with pytest.raises(RuntimeError, match="Google Translate unreachable"):
        _mod._synthesize_gtts("hello", "en", False)

    assert not Path(created_path["path"]).exists()  # cleaned up despite the failure
