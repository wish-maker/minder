"""Unit tests for tts-stt's speech_to_text route upload-size cap.

Found in a background audit: routes/stt.py's `await file.read()` (no size arg)
buffered an upload of ANY size fully into memory regardless of size, before
ffmpeg's own 30s timeout (core/stt_engine.py's _FFMPEG_TIMEOUT_S) ever got a
chance to bound anything. Mirrors rag-pipeline's own upload_document
size-cap pattern (tests/unit/test_rag_pipeline_retrieval.py).

Loaded by path, ONCE at module scope (not per-test, and not via a fixture
that re-loads for every test): routes/stt.py defines a module-level
prometheus Counter (stt_requests_total) -- reloading the module a second time
would re-register the same metric name against prometheus_client's global
default registry and raise DuplicateTimeseries. routes/stt.py's bare imports
(core.stt_engine/models/config) are collision-prone names shared with other
services' own same-named modules already cached in sys.modules within the
shared conftest.py test process -- stub/load them, exec the route module
ONCE, then immediately restore sys.modules (same one-shot save/stub/restore
precedent as test_graph_rag_knowledge_graph_handler.py's `_isolated_import`,
called exactly once at module scope there too). The resulting module object
keeps working fine afterward since its `from x import y` bindings are already
resolved into its own namespace by then.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "tts-stt"

_COLLISION_PRONE_NAMES = ("core", "core.stt_engine", "models", "config")


def _load_stt_routes():
    saved = {}
    for name in _COLLISION_PRONE_NAMES:
        saved[name] = sys.modules.pop(name, None)
    try:
        sys.modules["core"] = ModuleType("core")
        fake_stt_engine = ModuleType("core.stt_engine")
        fake_stt_engine.STT_AVAILABLE = True
        fake_stt_engine.transcribe = lambda audio_bytes, language: ("hello", 0.9)
        sys.modules["core.stt_engine"] = fake_stt_engine

        config_spec = importlib.util.spec_from_file_location(
            "config", _SERVICE_DIR / "config.py"
        )
        config_mod = importlib.util.module_from_spec(config_spec)
        sys.modules["config"] = config_mod
        config_spec.loader.exec_module(config_mod)

        models_spec = importlib.util.spec_from_file_location(
            "models", _SERVICE_DIR / "models" / "__init__.py"
        )
        models_mod = importlib.util.module_from_spec(models_spec)
        sys.modules["models"] = models_mod
        models_spec.loader.exec_module(models_mod)

        route_spec = importlib.util.spec_from_file_location(
            "tts_stt_routes_stt", _SERVICE_DIR / "routes" / "stt.py"
        )
        route_mod = importlib.util.module_from_spec(route_spec)
        route_spec.loader.exec_module(route_mod)
        return route_mod
    finally:
        for name in _COLLISION_PRONE_NAMES:
            sys.modules.pop(name, None)
            if saved[name] is not None:
                sys.modules[name] = saved[name]


_mod = _load_stt_routes()


class _FakeUploadFile:
    def __init__(self, data: bytes, filename: str = "clip.wav"):
        self._data = data
        self.filename = filename

    async def read(self, size=None):
        if size is None:
            return self._data
        return self._data[:size]


@pytest.mark.asyncio
async def test_speech_to_text_rejects_audio_over_the_configured_limit(monkeypatch):
    monkeypatch.setattr(_mod.settings, "STT_MAX_AUDIO_SIZE_MB", 0)

    with pytest.raises(Exception) as exc_info:
        await _mod.speech_to_text(
            file=_FakeUploadFile(b"way more than zero bytes"), language="tr-TR"
        )

    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_speech_to_text_passes_within_limit_audio_through(monkeypatch):
    monkeypatch.setattr(_mod.settings, "STT_MAX_AUDIO_SIZE_MB", 1)

    result = await _mod.speech_to_text(
        file=_FakeUploadFile(b"small clip"), language="tr-TR"
    )

    assert result.text == "hello"
    assert result.confidence == 0.9
