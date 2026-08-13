# tts-stt

Text-to-speech and speech-to-text (`:8006`, FastAPI, ~610 LOC). TTS runs **Piper
offline** by default (WAV) with a **gTTS online** fallback (MP3); STT uses
`speech_recognition`. Defaults to Turkish, English also bundled. Interactive docs
at `/docs`.

## Run / check

```bash
bash setup.sh start tts-stt        # Piper voices + espeak-ng baked into the image

curl http://localhost:8006/health
curl http://localhost:8006/v1/tts/languages           # supported TTS langs
curl -X POST http://localhost:8006/v1/tts \
     -H 'Content-Type: application/json' \
     -d '{"text":"Merhaba dünya","language":"tr"}' --output hello.wav

python scripts/dev/dev.py mypy tts-stt
python -m pytest tests/unit/test_tts_stt_*.py
```

## Endpoints (see `/docs` for schemas)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/v1/tts` | Synthesize speech from `text` (+ `language`). Piper → **WAV**; gTTS fallback → **MP3** |
| GET | `/v1/tts/languages` | Languages available for TTS |
| POST | `/v1/stt` | Transcribe an uploaded audio file → text |
| GET | `/v1/stt/languages` | Languages available for STT |

Every route is served at both `/v1/...` and the legacy unversioned path.

## Engines

- **TTS** (`core/tts_engine.py`): a **pluggable** engine. Piper is the offline
  default — bundled voices `en_US-lessac-low` (en) and `tr_TR-dfki-medium` (tr),
  so Turkish works fully offline (needs `espeak-ng` in the image). When Piper
  can't run, it falls back to gTTS (online, MP3). XTTS/Chatterbox/Bark were
  rejected for the Pi (GPU/license); the engine stays pluggable for a future GPU
  host (#18).
- **STT** (`core/stt_engine.py`): `speech_recognition`.

## Layout

```
tts-stt/
├── main.py               # thin app: include tts + stt routers
├── routes/
│   ├── tts.py            # /v1/tts + /v1/tts/languages
│   └── stt.py            # /v1/stt + /v1/stt/languages
├── core/
│   ├── tts_engine.py     # pluggable TTS (Piper offline / gTTS fallback)
│   └── stt_engine.py     # speech_recognition
├── models/__init__.py    # Pydantic request/response models
└── config.py             # Settings (default langs, voices dir, Piper voice IDs)
```

## Configuration (`config.py`)

- `DEFAULT_TTS_LANG` (`tr`), `DEFAULT_STT_LANG` (`tr-TR`).
- `TTS_VOICES_DIR` (`/app/voices`) — where the bundled Piper voices live.
- `TTS_PIPER_VOICE_EN` (`en_US-lessac-low`), `TTS_PIPER_VOICE_TR`
  (`tr_TR-dfki-medium`) — the `PIPER_VOICES` map; `SUPPORTED_LANGUAGES` /
  `SUPPORTED_STT_LANGUAGES` list what's offered.

No secrets, no DB — this service is self-contained (writes are JWT-gated at the
api-gateway proxy).

## Error conventions

Platform-wide `{"detail": ...}` shape; an unsupported language / bad audio → a
clean 4xx. See
**[`docs/api/reference.md` → Error Handling](../../../docs/api/reference.md)**.

## Tests

`tests/unit/test_tts_stt_*.py` — the TTS engine selection (Piper vs gTTS fallback),
language validation, and STT transcription with the audio backends faked (loaded
by-path per the one-process conftest harness).
