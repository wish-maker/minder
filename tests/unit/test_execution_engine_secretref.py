"""Unit tests for execute_webhook_trigger's secretRef fail-closed handling
(plugin-registry/core/execution_engine, #270).

secretRef was previously logged (`Would validate secret: ...`) and then
silently ignored -- a no-op that gave the caller no actual verification that
a plugin action's declared secret reference was valid/authorized. No secrets
store exists yet to validate against, so -- matching the existing fail-closed
precedent in webhooks.py's handle_webhook_request() (#47) -- a declared
secretRef is now rejected rather than silently passed through.

execution_engine imports only stdlib + httpx, so it loads by path with no
injection (same precedent as test_execution_engine_template.py).
"""

import importlib.util
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "core"
    / "execution_engine.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("execution_engine_under_test", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ExecutionEngine = _load().ExecutionEngine


def _manifest(*, secret_ref=None, action_type="store-vector"):
    webhook: dict = {"path": "/test"}
    if secret_ref is not None:
        webhook["secretRef"] = secret_ref
    return {
        "metadata": {"name": "test-plugin"},
        "spec": {
            "trigger": {"type": "webhook", "webhook": webhook},
            "action": {"type": action_type},
        },
    }


@pytest.mark.asyncio
async def test_secret_ref_declared_fails_closed():
    engine = ExecutionEngine()
    result = await engine.execute_webhook_trigger(
        _manifest(secret_ref="vault://plugin-secret"), {}
    )

    assert result["status"] == "error"
    assert "secretRef" in result["error"]
    assert "vault://plugin-secret" in result["error"]
    assert "not implemented" in result["error"]


@pytest.mark.asyncio
async def test_secret_ref_declared_never_reaches_action_handler(monkeypatch):
    engine = ExecutionEngine()
    called = []
    monkeypatch.setitem(
        engine._action_handlers,
        "store-vector",
        lambda *a: called.append(a) or {},
    )

    await engine.execute_webhook_trigger(
        _manifest(secret_ref="vault://plugin-secret"), {"text": "hello"}
    )

    assert called == []  # fail-closed before the action ever runs


@pytest.mark.asyncio
async def test_no_secret_ref_reaches_action_handler(monkeypatch):
    engine = ExecutionEngine()

    async def _fake_handler(manifest, data):
        return {"ok": True}

    monkeypatch.setitem(engine._action_handlers, "store-vector", _fake_handler)

    result = await engine.execute_webhook_trigger(_manifest(), {"text": "hello"})

    assert result["status"] == "success"
    assert result["result"] == {"ok": True}
