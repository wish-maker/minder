"""Unit tests filling core/webhooks.py's remaining coverage gaps (77%).

test_plugin_registry_webhook_persistence.py already covers manifest
persistence, startup restoration, and the body-size guard (both tests stop
at the secretRef 501 check, never reaching the actual execution). This adds:
register_plugin_webhook's no-webhook-path branch, handle_webhook_request's
404 (no route registered) and 500 (manifest not loaded) branches, form-data
parsing, the malformed-body 400 branch, and the full execution path
(success and the executor's own status=="error" -> 500 branch) --
previously entirely untested.

Same _fresh_import pattern as the sibling suite (no sys.path/sys.modules
cleanup -- matches that file's own established convention for this module).
"""

import importlib
import sys
from pathlib import Path

import pytest

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-registry"
)


def _fresh_import(module_path: str):
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    for stale in list(sys.modules):
        if (
            stale == "core"
            or stale.startswith("core.")
            or stale in ("config", "models")
        ):
            del sys.modules[stale]
    return importlib.import_module(module_path)


webhooks = _fresh_import("core.webhooks")


class _FakeRequest:
    def __init__(self, body: bytes, content_type="application/json", json_data=None):
        self._body = body
        self._json = json_data if json_data is not None else {}
        self.headers = {"content-type": content_type}

    async def body(self):
        return self._body

    async def json(self):
        return self._json

    async def form(self):
        return {"key": "value"}


# --- register_plugin_webhook: no webhook path --------------------------------


@pytest.mark.asyncio
async def test_register_plugin_webhook_warns_and_skips_when_no_path(monkeypatch):
    monkeypatch.setattr(webhooks, "webhook_routes", {})
    manifest = {
        "metadata": {"name": "weather"},
        "spec": {"trigger": {"type": "webhook", "webhook": {}}},  # no "path"
    }

    await webhooks.register_plugin_webhook("weather", manifest)

    assert webhooks.webhook_routes == {}  # nothing registered


# --- handle_webhook_request: routing / manifest-loaded gates -----------------


@pytest.mark.asyncio
async def test_handle_webhook_request_404_when_no_route_registered(monkeypatch):
    monkeypatch.setattr(webhooks, "webhook_routes", {})

    with pytest.raises(webhooks.HTTPException) as exc:
        await webhooks.handle_webhook_request("/webhook/unknown", _FakeRequest(b"{}"))

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_handle_webhook_request_500_when_manifest_not_loaded(monkeypatch):
    monkeypatch.setattr(webhooks, "webhook_routes", {"/webhook/w": "p1"})
    monkeypatch.setattr(webhooks, "plugin_manifests", {})  # no manifest for p1

    with pytest.raises(webhooks.HTTPException) as exc:
        await webhooks.handle_webhook_request("/webhook/w", _FakeRequest(b"{}"))

    assert exc.value.status_code == 500
    assert "manifest not loaded" in exc.value.detail


# --- handle_webhook_request: body parsing ------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_request_parses_form_data(monkeypatch):
    monkeypatch.setattr(webhooks, "webhook_routes", {"/webhook/w": "p1"})
    monkeypatch.setattr(
        webhooks,
        "plugin_manifests",
        {"p1": {"spec": {"trigger": {"webhook": {"secretRef": "x"}}}}},
    )

    # No secretRef verification implemented -> 501, but only AFTER parsing --
    # proves form-data (non-JSON content-type) was parsed without error.
    with pytest.raises(webhooks.HTTPException) as exc:
        await webhooks.handle_webhook_request(
            "/webhook/w",
            _FakeRequest(
                b"key=value", content_type="application/x-www-form-urlencoded"
            ),
        )

    assert exc.value.status_code == 501


class _MalformedJsonRequest(_FakeRequest):
    async def json(self):
        raise ValueError("malformed JSON")


@pytest.mark.asyncio
async def test_handle_webhook_request_400_on_malformed_body(monkeypatch):
    monkeypatch.setattr(webhooks, "webhook_routes", {"/webhook/w": "p1"})
    monkeypatch.setattr(webhooks, "plugin_manifests", {"p1": {"spec": {}}})

    with pytest.raises(webhooks.HTTPException) as exc:
        await webhooks.handle_webhook_request(
            "/webhook/w", _MalformedJsonRequest(b"{not json")
        )

    assert exc.value.status_code == 400
    assert "Failed to parse webhook data" in exc.value.detail


# --- handle_webhook_request: the actual execution path -----------------------


@pytest.fixture
def execution_engine_mod():
    return importlib.import_module("core.execution_engine")


@pytest.mark.asyncio
async def test_handle_webhook_request_success_returns_processed_result(
    monkeypatch, execution_engine_mod
):
    monkeypatch.setattr(webhooks, "webhook_routes", {"/webhook/w": "p1"})
    monkeypatch.setattr(webhooks, "plugin_manifests", {"p1": {"spec": {}}})

    class _FakeEngine:
        async def execute_webhook_trigger(self, manifest, webhook_data):
            return {"status": "success", "result": {"point_id": "abc"}}

    monkeypatch.setattr(
        execution_engine_mod, "get_execution_engine", lambda: _FakeEngine()
    )

    result = await webhooks.handle_webhook_request(
        "/webhook/w", _FakeRequest(b'{"msg": "hi"}', json_data={"msg": "hi"})
    )

    assert result["message"] == "Webhook processed successfully"
    assert result["plugin"] == "p1"
    assert result["result"] == {"point_id": "abc"}


@pytest.mark.asyncio
async def test_handle_webhook_request_500_when_executor_reports_error(
    monkeypatch, execution_engine_mod
):
    monkeypatch.setattr(webhooks, "webhook_routes", {"/webhook/w": "p1"})
    monkeypatch.setattr(webhooks, "plugin_manifests", {"p1": {"spec": {}}})

    class _FakeEngine:
        async def execute_webhook_trigger(self, manifest, webhook_data):
            return {"status": "error", "error": "downstream failure"}

    monkeypatch.setattr(
        execution_engine_mod, "get_execution_engine", lambda: _FakeEngine()
    )

    with pytest.raises(webhooks.HTTPException) as exc:
        await webhooks.handle_webhook_request(
            "/webhook/w", _FakeRequest(b'{"msg": "hi"}', json_data={"msg": "hi"})
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == "downstream failure"
