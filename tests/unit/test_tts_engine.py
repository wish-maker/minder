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
from types import ModuleType
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


def test_resolve_voice_id_returns_none_for_unconfigured_language(monkeypatch):
    monkeypatch.setattr(
        _mod, "PIPER_VOICES", {"en": {"default": {"model": "en_US-lessac-low"}}}
    )
    assert _mod._resolve_voice_id("de", None) is None


def test_piper_voice_path_none_when_resolve_voice_id_yields_none(monkeypatch):
    # Guards the (currently unreachable in practice, since _piper_voice_path's
    # own `if not voices` already short-circuits first) defensive None-check
    # on voice_id -- exercised directly here in case that invariant ever
    # changes.
    monkeypatch.setattr(
        _mod, "PIPER_VOICES", {"en": {"default": {"model": "en_US-lessac-low"}}}
    )
    monkeypatch.setattr(_mod, "_resolve_voice_id", lambda language, voice: None)
    assert _mod._piper_voice_path("en", None) is None


def test_load_piper_returns_none_when_no_voice_path(monkeypatch):
    monkeypatch.setattr(_mod, "_piper_cache", {})
    monkeypatch.setattr(_mod, "_resolve_voice_id", lambda lang, voice: "default")
    monkeypatch.setattr(_mod, "_piper_voice_path", lambda lang, voice: None)
    assert _mod._load_piper("de", None) is None


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


def test_load_piper_concurrent_first_use_loads_the_voice_only_once(monkeypatch):
    """Found in a background audit: synthesize() (and so _load_piper) runs via
    asyncio.to_thread, so concurrent first-use requests for the same voice run
    in separate real OS threads. The old bare check-then-set on a plain dict
    let two threads both see a cache miss and both pay for a full
    PiperVoice.load() -- confirm the lock actually serializes this: force the
    "loader" to block until BOTH threads have called _load_piper, so a broken
    (unlocked) version would call PiperVoice.load() twice."""
    import threading
    import time

    monkeypatch.setattr(_mod, "_piper_cache", {})
    monkeypatch.setattr(_mod, "_resolve_voice_id", lambda lang, voice: "default")
    monkeypatch.setattr(
        _mod, "_piper_voice_path", lambda lang, voice: "/voices/tr.onnx"
    )

    load_calls = []
    first_call_entered = threading.Event()

    def slow_load(path):
        load_calls.append(path)
        first_call_entered.set()
        time.sleep(0.05)  # give a second thread a chance to race in
        return MagicMock()

    results = []

    def worker():
        results.append(_mod._load_piper("tr", None))

    with patch.object(_mod, "PiperVoice", create=True) as piper_cls:
        piper_cls.load = slow_load
        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        first_call_entered.wait(timeout=2)
        t2.start()
        t1.join(timeout=2)
        t2.join(timeout=2)

    assert len(load_calls) == 1  # only ONE PiperVoice.load(), not two
    assert results[0] is results[1]  # both threads got the same cached instance


def test_synthesize_piper_returns_none_when_no_voice_loaded(monkeypatch):
    monkeypatch.setattr(_mod, "_load_piper", lambda language, voice: None)
    assert _mod._synthesize_piper("hello", "en", False, None) is None


def _fake_synthesize_wav(text, wf, syn_config=None):
    """Duck-types PiperVoice.synthesize_wav enough to produce real WAV bytes."""
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)
    wf.writeframes(b"\x00\x00")


def test_synthesize_piper_falls_back_when_synthesisconfig_unavailable(monkeypatch):
    # piper isn't installed in this test environment, so the function's own
    # local `from piper import SynthesisConfig` always raises ImportError here
    # -- exercises the except-branch fallback call (no syn_config kwarg passed
    # at all), matching what happens in production against any piper-tts
    # version that predates SynthesisConfig.
    fake_voice = MagicMock()
    fake_voice.synthesize_wav.side_effect = _fake_synthesize_wav
    monkeypatch.setattr(_mod, "_load_piper", lambda language, voice: fake_voice)

    data = _mod._synthesize_piper("hello", "en", True, None)

    assert data.startswith(b"RIFF")  # real WAV bytes
    args, kwargs = fake_voice.synthesize_wav.call_args
    assert "syn_config" not in kwargs


def test_synthesize_piper_uses_synthesisconfig_when_slow(monkeypatch):
    fake_voice = MagicMock()
    fake_voice.synthesize_wav.side_effect = _fake_synthesize_wav
    monkeypatch.setattr(_mod, "_load_piper", lambda language, voice: fake_voice)

    class _FakeSynthesisConfig:
        def __init__(self, length_scale=None):
            self.length_scale = length_scale

    fake_piper_module = ModuleType("piper")
    fake_piper_module.SynthesisConfig = _FakeSynthesisConfig
    monkeypatch.setitem(sys.modules, "piper", fake_piper_module)

    data = _mod._synthesize_piper("hello", "en", True, None)

    assert data.startswith(b"RIFF")
    _, kwargs = fake_voice.synthesize_wav.call_args
    assert kwargs["syn_config"].length_scale == 1.5


def test_synthesize_piper_passes_no_length_scale_when_not_slow(monkeypatch):
    fake_voice = MagicMock()
    fake_voice.synthesize_wav.side_effect = _fake_synthesize_wav
    monkeypatch.setattr(_mod, "_load_piper", lambda language, voice: fake_voice)

    class _FakeSynthesisConfig:
        def __init__(self, length_scale=None):
            self.length_scale = length_scale

    fake_piper_module = ModuleType("piper")
    fake_piper_module.SynthesisConfig = _FakeSynthesisConfig
    monkeypatch.setitem(sys.modules, "piper", fake_piper_module)

    data = _mod._synthesize_piper("hello", "en", False, None)

    assert data.startswith(b"RIFF")
    _, kwargs = fake_voice.synthesize_wav.call_args
    assert kwargs["syn_config"] is None


def test_synthesize_gtts_returns_bytes_and_cleans_up_temp_file(monkeypatch, tmp_path):
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
        open(path, "wb").close()
        created_path["path"] = path
        return _FakeTempFile(path)

    monkeypatch.setattr(_mod.tempfile, "NamedTemporaryFile", fake_named_temp_file)

    class _FakeGTTS:
        def __init__(self, **kwargs):
            pass

        def save(self, path):
            with open(path, "wb") as f:
                f.write(b"fake-mp3-bytes")

    monkeypatch.setattr(_mod, "gTTS", _FakeGTTS, raising=False)

    data = _mod._synthesize_gtts("hello", "en", False)

    assert data == b"fake-mp3-bytes"
    assert not Path(created_path["path"]).exists()


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
