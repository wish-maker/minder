"""Regression guard for tts-stt's STT language-validation mismatch.

`routes/stt.py` used to validate the `language` field against
`SUPPORTED_LANGUAGES` (TTS's bare 2-letter codes, e.g. "tr") -- but
`core/stt_engine.py`'s `recognize_google(audio, language=...)` call actually
needs a BCP-47 locale code (e.g. "tr-TR"). That mismatch meant
`DEFAULT_STT_LANG` ("tr-TR") failed its OWN route's validation, and any
caller passing the locale-qualified code Google actually requires got
rejected too. Fixed by adding a separate `SUPPORTED_STT_LANGUAGES` (BCP-47)
and validating STT against that instead.

Several sibling services ship a bare `config.py`; force-load tts-stt's under
the `config` module name so whichever one the shared root conftest.py
happened to import first doesn't win, mirroring
test_rag_ollama_failover_error.py's established pattern.
"""

import importlib.util
import re
import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "tts-stt"


def _load_config():
    saved = sys.modules.get("config")
    spec = importlib.util.spec_from_file_location("config", _SERVICE_DIR / "config.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["config"] = mod
    try:
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def test_default_stt_lang_is_itself_a_supported_stt_language():
    config = _load_config()
    assert config.settings.DEFAULT_STT_LANG in config.SUPPORTED_STT_LANGUAGES


def test_supported_stt_languages_are_bcp47_locale_codes():
    """Every STT language code must be locale-qualified (e.g. "tr-TR"), the
    format recognize_google() actually requires -- distinct from TTS's bare
    2-letter SUPPORTED_LANGUAGES ("tr")."""
    config = _load_config()
    for code in config.SUPPORTED_STT_LANGUAGES:
        assert re.fullmatch(r"[a-z]{2}-[A-Z]{2}", code), f"not a BCP-47 code: {code!r}"


def test_stt_and_tts_language_sets_cover_the_same_languages():
    """Same eleven languages, just different code formats -- catches a typo
    that silently drops or duplicates a language between the two sets."""
    config = _load_config()
    assert set(config.SUPPORTED_LANGUAGES.values()) == set(
        config.SUPPORTED_STT_LANGUAGES.values()
    )
