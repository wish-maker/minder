# model-management

Ollama model lifecycle for Minder (`:8005`, FastAPI, ~630 LOC). List, pull,
inspect, delete, and smoke-test local LLMs. It talks **only to Ollama** — no
Postgres/Redis/JWT — so it uses a plain `BaseSettings` with a single
`OLLAMA_HOST`. Interactive docs at `/docs`.

## Run / check

```bash
bash setup.sh start model-management     # needs a reachable Ollama at OLLAMA_HOST

curl http://localhost:8005/health
curl http://localhost:8005/v1/models                          # list (paginated envelope)
curl -X POST http://localhost:8005/v1/models \
     -H 'Content-Type: application/json' -d '{"model_id":"llama3.2"}'   # pull → 201

python scripts/dev/dev.py mypy model-management
python -m pytest tests/unit/test_model_management_*.py
```

## Endpoints (see `/docs` for schemas)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/v1/models` | List installed models — `{items,total,limit,offset}` envelope (#501) |
| POST | `/v1/models` | Pull a model — body `{"model_id": "..."}` → **201**. Rejects a custom registry host (**422**) — only the default Ollama library, optionally namespaced (e.g. `namespace/model:tag`), is supported (#679). Concurrent pulls capped via `MAX_CONCURRENT_MODEL_PULLS` |
| GET | `/v1/models/{model_id}` | Inspect one model (details from Ollama) |
| DELETE | `/v1/models/{model_id}` | Delete a model |
| POST | `/v1/models/{model_id}/test` | Smoke-test: send a prompt, return the completion. Requires auth (any role) + rate-limited 5/min per user (#746) |
| POST | `/v1/models/{model_id}/constraints` | **501 — not implemented** (#145) |
| GET | `/v1/models/{model_id}/metrics` | **501 — not implemented** (#145) |
| POST | `/v1/models/fine-tune` | **501 — not implemented** (#145) |

Every route is served at both `/v1/...` and the legacy unversioned path.
Constraints / metrics / fine-tune are deliberate 501 stubs — the fine-tuning
service was removed on purpose (do NOT re-add), and these return a clear
"not implemented" rather than pretending.

## Layout

```
model-management/
├── main.py                  # thin app: include the models router
├── routes/models_api.py     # all endpoints (list/pull/get/delete/test + 501 stubs)
├── core/ollama_manager.py   # the Ollama client (list/pull/show/delete/generate)
├── models/__init__.py       # Pydantic request/response models (ModelInfo, ...)
└── config.py                # Settings: OLLAMA_HOST, MAX_CONCURRENT_MODEL_PULLS
```

## Configuration (`config.py`)

- `OLLAMA_HOST` (default `http://ollama:11434`) — the Ollama runtime. Follows the
  platform `OLLAMA_HOST` convention: empty/local → the internal `minder-ollama`
  container; set → an external/native host (resolve as `host.docker.internal` /
  LAN-IP from inside the container, not `localhost`).
- `MAX_CONCURRENT_MODEL_PULLS` (default `1`) — caps concurrent `pull_model` calls
  via an `asyncio.Semaphore` (#679). Each pull can be many GB with no
  disk-space check; the default serializes pulls entirely so unbounded
  concurrent downloads can't race to fill the shared Ollama volume.

No secrets. Writes are JWT-gated at the api-gateway proxy (#47) — except `test_model`
(the most compute-expensive endpoint here), which also carries its own direct
`get_current_user` dependency + a 5-requests/minute-per-user rate limit (#746), as
defense-in-depth beyond the gateway's own check.

## Error conventions

Platform-wide `{"detail": ...}` shape; an unreachable Ollama surfaces as a
backend-down 503 rather than a raw 500. See
**[`docs/api/reference.md` → Error Handling](../../../docs/api/reference.md)**.

## Tests

`tests/unit/test_model_management_*.py` — the list/pull/delete/test flows and the
paginated envelope, with the Ollama client faked (loaded by-path per the
one-process conftest harness).
