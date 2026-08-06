"""Unit tests for model-management's error handling (#357).

#357: every route in models_api.py caught a generic Exception and returned
`HTTPException(503, detail=f"Failed to X: {str(e)}")` -- leaking the raw
driver/ollama exception string to the API client, and always using 503 even
for a genuine bug (not just "backend unreachable"). Switched to
shared.errors.backend_http_error, which classifies connectivity failures as
503 with a sanitized message and everything else as 500 -- never returning
str(e) to the caller.

Loaded via sys.path + a stale-cache clear (conftest.py loads every service's
main.py into ONE shared pytest process) -- matching this session's
established precedent.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "model-management"
)

_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(module_path: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)

    sys.path.insert(0, str(_SERVICE_DIR))
    import importlib

    try:
        return importlib.import_module(module_path)
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def _client(ollama_manager):
    models_api = _isolated_import("routes.models_api")
    app = FastAPI()
    app.include_router(
        models_api.build_models_router(
            ollama_manager=ollama_manager, models={}, logger=_NoopLogger()
        )
    )
    return TestClient(app, raise_server_exceptions=False)


def test_connectivity_failure_returns_503_without_leaking_exception_text():
    secret_looking_detail = (
        "postgresql://minder:s3cr3t-password@10.0.0.5:5432/minder is unreachable"
    )
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(side_effect=ConnectionError(secret_looking_detail))},
    )()

    r = _client(ollama_manager).get("/models")

    assert r.status_code == 503
    assert secret_looking_detail not in r.text
    assert "unreachable" in r.json()["detail"].lower()


def test_generic_bug_returns_500_without_leaking_exception_text():
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(side_effect=KeyError("some_internal_field"))},
    )()

    r = _client(ollama_manager).get("/models")

    assert r.status_code == 500
    assert "some_internal_field" not in r.text


def test_list_models_success_path_unaffected():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(
                return_value=[{"model": "llama3.2:latest", "size": 123}]
            )
        },
    )()

    r = _client(ollama_manager).get("/models")

    assert r.status_code == 200
    assert r.json()[0]["id"] == "llama3.2:latest"
