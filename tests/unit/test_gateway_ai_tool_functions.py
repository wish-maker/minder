"""Unit tests for api-gateway's routes/ai.py -- get_tool_definitions (the
60s-TTL tool-definition cache with a stale-cache-on-fetch-failure fallback),
_call_plugin_tool (proxies a tool invocation to its plugin endpoint), and
execute_function (POST /v1/ai/functions/{function_name}). All three were
only ever mocked out (never directly exercised) in
test_gateway_tool_args.py / test_gateway_tools_openapi.py /
test_api_gateway_chat_error_handling.py.

Reuses those files' fresh-import fixture exactly (a brand new module object
per test via spec_from_file_location, so get_tool_definitions' module-level
_tools_cache/_tools_cache_time globals start pristine every time -- no
cross-test cache pollution).

api-gateway is a hyphenated service dir; ai.py imports ``from config import
settings`` and ``from core.auth import get_current_user_required`` at module
top -- fakes for both are injected and restored.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "routes"
    / "ai.py"
)


@pytest.fixture
def ai_mod():
    names = ("config", "core", "core.auth")
    saved = {n: sys.modules.get(n) for n in names}
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(
        PLUGIN_REGISTRY_URL="http://reg:8001",
        RAG_PIPELINE_URL="http://rag:8004",
    )
    sys.modules["config"] = cfg
    sys.modules["core"] = ModuleType("core")
    fake_core_auth = ModuleType("core.auth")

    async def _fake_get_current_user_required(request):
        return {"sub": "test-user"}

    fake_core_auth.get_current_user_required = _fake_get_current_user_required
    sys.modules["core.auth"] = fake_core_auth
    try:
        spec = importlib.util.spec_from_file_location("ai_under_test_2", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for n, m in saved.items():
            if m is not None:
                sys.modules[n] = m
            else:
                sys.modules.pop(n, None)


class _FakeResponse:
    def __init__(self, json_body=None, raises=None):
        self._json_body = json_body if json_body is not None else {}
        self._raises = raises

    def raise_for_status(self):
        if self._raises:
            raise self._raises

    def json(self):
        return self._json_body


class _FakeAsyncClient:
    def __init__(
        self,
        get_response=None,
        post_response=None,
        raises=None,
        get_responses_by_url_prefix=None,
    ):
        self._get_response = get_response
        self._post_response = post_response
        self._raises = raises
        # get_tool_definitions now fetches two URLs (plugin-registry tools +
        # rag-pipeline pipelines); tests that care about both responses at
        # once pass this instead of the single get_response fallback.
        self._get_responses_by_url_prefix = get_responses_by_url_prefix or {}
        self.get_calls = []
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if self._raises:
            raise self._raises
        for prefix, resp in self._get_responses_by_url_prefix.items():
            if url.startswith(prefix):
                return resp
        return self._get_response

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if self._raises:
            raise self._raises
        return self._post_response


def _patch_httpx(monkeypatch, ai_mod, client):
    monkeypatch.setattr(ai_mod.httpx, "AsyncClient", lambda *a, **k: client)


# --- get_tool_definitions -----------------------------------------------------


@pytest.mark.asyncio
async def test_fetches_fresh_when_no_cache(ai_mod, monkeypatch):
    # get_tool_definitions now fetches both plugin-registry tools AND
    # rag-pipeline's pipeline list (merged into one cached result) -- the
    # pipeline fetch's response here has no "items" key, so it contributes
    # zero pipeline-derived tools and the merged result is just the plugin
    # tools, unchanged from before this feature existed.
    fake_client = _FakeAsyncClient(get_response=_FakeResponse({"tools": ["a"]}))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    result = await ai_mod.get_tool_definitions()

    assert result == {"tools": ["a"]}
    assert len(fake_client.get_calls) == 2


@pytest.mark.asyncio
async def test_pipeline_tools_are_owner_scoped_when_owner_given(ai_mod, monkeypatch):
    """#943: get_tool_definitions(owner_user_id=...) must pass that id to the
    rag-pipeline list so only the caller's own pipelines become ask_* tools."""
    fake_client = _FakeAsyncClient(
        get_responses_by_url_prefix={
            ai_mod.settings.PLUGIN_REGISTRY_URL: _FakeResponse({"tools": []}),
            ai_mod.settings.RAG_PIPELINE_URL: _FakeResponse({"items": []}),
        }
    )
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    await ai_mod.get_tool_definitions(owner_user_id="alice")

    pipeline_gets = [
        kwargs
        for (url, kwargs) in fake_client.get_calls
        if url.startswith(ai_mod.settings.RAG_PIPELINE_URL)
    ]
    assert pipeline_gets, "rag-pipeline list was not fetched"
    assert pipeline_gets[0]["params"].get("owner_user_id") == "alice"


@pytest.mark.asyncio
async def test_pipeline_tools_unscoped_when_no_owner(ai_mod, monkeypatch):
    """No owner (the discovery/OpenAPI endpoints) -> no owner_user_id param, so
    all pipelines are listed (query-time enforcement still protects the data)."""
    fake_client = _FakeAsyncClient(
        get_responses_by_url_prefix={
            ai_mod.settings.PLUGIN_REGISTRY_URL: _FakeResponse({"tools": []}),
            ai_mod.settings.RAG_PIPELINE_URL: _FakeResponse({"items": []}),
        }
    )
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    await ai_mod.get_tool_definitions()

    pipeline_gets = [
        kwargs
        for (url, kwargs) in fake_client.get_calls
        if url.startswith(ai_mod.settings.RAG_PIPELINE_URL)
    ]
    assert pipeline_gets
    assert "owner_user_id" not in pipeline_gets[0]["params"]


@pytest.mark.asyncio
async def test_returns_cached_value_within_ttl_without_refetching(ai_mod, monkeypatch):
    import time

    ai_mod._tools_cache = {"tools": ["cached"]}
    ai_mod._tools_cache_time = time.time()
    fake_client = _FakeAsyncClient(
        get_response=_FakeResponse({"tools": ["should-not-be-returned"]})
    )
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    result = await ai_mod.get_tool_definitions()

    # Plugin tools come from cache (no plugin-registry refetch), but the
    # owner-scoped pipeline defs are always fetched fresh (#943) -- they can't
    # share the global cache without leaking one user's pipelines to another.
    # The pipeline response here has no "items", so the merged result is just
    # the cached plugin tools.
    assert result == {"tools": ["cached"]}
    assert len(fake_client.get_calls) == 1
    assert fake_client.get_calls[0][0].startswith(ai_mod.settings.RAG_PIPELINE_URL)


@pytest.mark.asyncio
async def test_refetches_once_the_ttl_expires(ai_mod, monkeypatch):
    import time

    ai_mod._tools_cache = {"tools": ["stale"]}
    ai_mod._tools_cache_time = time.time() - (ai_mod.CACHE_TTL + 1)
    fake_client = _FakeAsyncClient(get_response=_FakeResponse({"tools": ["fresh"]}))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    result = await ai_mod.get_tool_definitions()

    assert result == {"tools": ["fresh"]}
    assert len(fake_client.get_calls) == 2


@pytest.mark.asyncio
async def test_falls_back_to_stale_cache_on_fetch_failure(ai_mod, monkeypatch):
    import time

    ai_mod._tools_cache = {"tools": ["stale-but-usable"]}
    ai_mod._tools_cache_time = time.time() - (ai_mod.CACHE_TTL + 1)
    fake_client = _FakeAsyncClient(raises=httpx.ConnectError("registry down"))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    result = await ai_mod.get_tool_definitions()

    assert result == {"tools": ["stale-but-usable"]}


@pytest.mark.asyncio
async def test_returns_empty_tools_on_failure_with_no_cache_at_all(ai_mod, monkeypatch):
    fake_client = _FakeAsyncClient(raises=httpx.ConnectError("registry down"))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    result = await ai_mod.get_tool_definitions()

    assert result == {"tools": []}


# --- _call_plugin_tool --------------------------------------------------------


@pytest.mark.asyncio
async def test_call_plugin_tool_missing_endpoint_metadata_is_500(ai_mod):
    with pytest.raises(HTTPException) as exc_info:
        await ai_mod._call_plugin_tool({})
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_call_plugin_tool_get_method_uses_params(ai_mod, monkeypatch):
    fake_client = _FakeAsyncClient(get_response=_FakeResponse({"ok": True}))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    result = await ai_mod._call_plugin_tool(
        {"endpoint": "/v1/plugins/weather/actions/current", "method": "GET"},
        params={"city": "Ankara"},
    )

    assert result == {"ok": True}
    url, kwargs = fake_client.get_calls[0]
    assert url == "http://reg:8001/v1/plugins/weather/actions/current"
    assert kwargs["params"] == {"city": "Ankara"}


@pytest.mark.asyncio
async def test_call_plugin_tool_defaults_to_post_with_json_body(ai_mod, monkeypatch):
    fake_client = _FakeAsyncClient(post_response=_FakeResponse({"ok": True}))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    await ai_mod._call_plugin_tool(
        {"endpoint": "/v1/plugins/crypto/actions/get_price"},
        json_body={"symbol": "BTC"},
    )

    url, kwargs = fake_client.post_calls[0]
    assert url == "http://reg:8001/v1/plugins/crypto/actions/get_price"
    assert kwargs["json"] == {"symbol": "BTC"}


@pytest.mark.asyncio
async def test_call_plugin_tool_forwards_the_auth_header(ai_mod, monkeypatch):
    fake_client = _FakeAsyncClient(post_response=_FakeResponse({}))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    await ai_mod._call_plugin_tool(
        {"endpoint": "/v1/plugins/x/actions/y"},
        auth_header="Bearer real-user-jwt",
    )

    _url, kwargs = fake_client.post_calls[0]
    assert kwargs["headers"] == {"Authorization": "Bearer real-user-jwt"}


@pytest.mark.asyncio
async def test_call_plugin_tool_propagates_downstream_http_errors(ai_mod, monkeypatch):
    fake_client = _FakeAsyncClient(
        post_response=_FakeResponse(
            raises=httpx.HTTPStatusError("500", request=None, response=None)
        )
    )
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    with pytest.raises(httpx.HTTPStatusError):
        await ai_mod._call_plugin_tool({"endpoint": "/v1/plugins/x/actions/y"})


# --- execute_function (POST /v1/ai/functions/{function_name}) ---------------


class _FakeRequest:
    def __init__(self, json_body=None, json_raises=None, query_params=None, auth=None):
        self._json_body = json_body
        self._json_raises = json_raises
        self.query_params = query_params or {}
        self.headers = {"Authorization": auth} if auth else {}

    async def json(self):
        if self._json_raises:
            raise self._json_raises
        return self._json_body


@pytest.mark.asyncio
async def test_execute_function_unknown_tool_is_404(ai_mod, monkeypatch):
    async def fake_get_tool_definitions():
        return {"tools": []}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)

    with pytest.raises(HTTPException) as exc_info:
        await ai_mod.execute_function("no_such_tool", _FakeRequest())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_execute_function_defaults_body_to_empty_dict_on_bad_json(
    ai_mod, monkeypatch
):
    captured = {}

    async def fake_get_tool_definitions():
        return {
            "tools": [
                {
                    "function": {"name": "get_weather"},
                    "metadata": {"endpoint": "/v1/plugins/weather/actions/current"},
                }
            ]
        }

    async def fake_call_plugin_tool(metadata, *, json_body=None, **kwargs):
        captured["json_body"] = json_body
        return {"temp": 20}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)

    request = _FakeRequest(json_raises=ValueError("not valid json"))
    result = await ai_mod.execute_function("get_weather", request)

    assert captured["json_body"] == {}
    assert result["status"] == "success"
    assert result["result"] == {"temp": 20}
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_execute_function_success_envelope(ai_mod, monkeypatch):
    async def fake_get_tool_definitions():
        return {
            "tools": [
                {
                    "function": {"name": "get_price"},
                    "metadata": {"endpoint": "/v1/plugins/crypto/actions/get_price"},
                }
            ]
        }

    async def fake_call_plugin_tool(metadata, **kwargs):
        return {"price": 42000}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)

    result = await ai_mod.execute_function(
        "get_price", _FakeRequest(json_body={"symbol": "BTC"})
    )

    assert result == {
        "result": {"price": 42000},
        "status": "success",
        "timestamp": result["timestamp"],
    }


@pytest.mark.asyncio
async def test_execute_function_routes_json_body_to_params_for_get_tools(
    ai_mod, monkeypatch
):
    """A real bug, found live 2026-08-19: a caller of POST /v1/ai/functions/{name}
    (exactly how the OpenAI function-calling convention this endpoint's own
    /functions/definitions schema implies would invoke it) sends arguments as a
    JSON body -- but for a GET-method tool (get_weather, get_crypto_price,
    get_fund_price, get_news), _call_plugin_tool only ever forwards `params`,
    silently dropping `json_body` entirely. Before this fix, execute_function
    always sent the caller's body as `json_body` regardless of the tool's
    method, so every GET tool called the standard way forwarded ZERO arguments
    downstream and 400'd. The internal chat-completions tool loop already
    routes this correctly (see the `is_get` branch there); this endpoint must
    match it."""
    captured = {}

    async def fake_get_tool_definitions():
        return {
            "tools": [
                {
                    "function": {"name": "get_weather"},
                    "metadata": {
                        "endpoint": "/v1/plugins/weather/actions/get_weather",
                        "method": "GET",
                    },
                }
            ]
        }

    async def fake_call_plugin_tool(metadata, *, json_body=None, params=None, **kwargs):
        captured["json_body"] = json_body
        captured["params"] = params
        return {"temp_c": 22}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)

    result = await ai_mod.execute_function(
        "get_weather", _FakeRequest(json_body={"location": "Istanbul"})
    )

    assert captured["params"] == {"location": "Istanbul"}
    assert captured["json_body"] is None
    assert result["result"] == {"temp_c": 22}


@pytest.mark.asyncio
async def test_execute_function_unwraps_a_parameters_envelope_for_get_tools(
    ai_mod, monkeypatch
):
    """Some models wrap tool arguments as {"parameters": {...}} (see
    _normalize_tool_args's own docstring) -- execute_function must unwrap that
    the same way the chat-completions loop already does, not just for POST
    tools but for the GET-routed params too."""
    captured = {}

    async def fake_get_tool_definitions():
        return {
            "tools": [
                {
                    "function": {"name": "get_weather"},
                    "metadata": {
                        "endpoint": "/v1/plugins/weather/actions/get_weather",
                        "method": "GET",
                    },
                }
            ]
        }

    async def fake_call_plugin_tool(metadata, *, json_body=None, params=None, **kwargs):
        captured["params"] = params
        return {}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)

    await ai_mod.execute_function(
        "get_weather",
        _FakeRequest(json_body={"parameters": {"location": "Tokyo"}}),
    )

    assert captured["params"] == {"location": "Tokyo"}


# --- _slugify_pipeline_name ---------------------------------------------------


def test_slugify_lowercases_and_collapses_symbols(ai_mod):
    assert ai_mod._slugify_pipeline_name("My KB!") == "my_kb"


def test_slugify_falls_back_when_nothing_alphanumeric_survives(ai_mod):
    assert ai_mod._slugify_pipeline_name("!!!") == "pipeline"


# --- _fetch_pipeline_function_defs (RAG pipeline chat-tool bridge) ----------


@pytest.mark.asyncio
async def test_fetch_pipeline_function_defs_builds_one_ask_tool_per_pipeline(
    ai_mod, monkeypatch
):
    fake_client = _FakeAsyncClient(
        get_response=_FakeResponse(
            {
                "items": [
                    {"id": "pipe-1", "name": "Docs KB"},
                    {"id": "pipe-2", "name": "Support Tickets"},
                ]
            }
        )
    )
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    defs = await ai_mod._fetch_pipeline_function_defs()

    names = [d["function"]["name"] for d in defs]
    assert names == ["ask_docs_kb", "ask_support_tickets"]
    first = defs[0]
    assert first["function"]["parameters"]["required"] == ["question"]
    assert first["metadata"] == {
        "endpoint": "/v1/pipeline/pipe-1/query",
        "method": "POST",
        "base_url": "http://rag:8004",
        "result_field": "answer",
        "kind": "rag_pipeline",
    }


@pytest.mark.asyncio
async def test_fetch_pipeline_function_defs_disambiguates_colliding_slugs(
    ai_mod, monkeypatch
):
    fake_client = _FakeAsyncClient(
        get_response=_FakeResponse(
            {
                "items": [
                    {"id": "pipe-1", "name": "Docs"},
                    {"id": "pipe-22222222", "name": "docs!"},
                ]
            }
        )
    )
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    defs = await ai_mod._fetch_pipeline_function_defs()

    names = {d["function"]["name"] for d in defs}
    assert names == {"ask_docs", "ask_docs_pipe-222"}


@pytest.mark.asyncio
async def test_fetch_pipeline_function_defs_degrades_to_empty_on_fetch_failure(
    ai_mod, monkeypatch
):
    fake_client = _FakeAsyncClient(raises=httpx.ConnectError("rag-pipeline down"))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    defs = await ai_mod._fetch_pipeline_function_defs()

    assert defs == []


# --- get_tool_definitions: merged plugin + pipeline tools --------------------


@pytest.mark.asyncio
async def test_get_tool_definitions_merges_plugin_and_pipeline_tools(
    ai_mod, monkeypatch
):
    fake_client = _FakeAsyncClient(
        get_responses_by_url_prefix={
            "http://reg:8001": _FakeResponse(
                {"tools": [{"function": {"name": "get_weather"}}]}
            ),
            "http://rag:8004": _FakeResponse(
                {"items": [{"id": "pipe-1", "name": "Docs"}]}
            ),
        }
    )
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    result = await ai_mod.get_tool_definitions()

    names = [t["function"]["name"] for t in result["tools"]]
    assert names == ["get_weather", "ask_docs"]


# --- _call_plugin_tool: base_url and result_field overrides ------------------


@pytest.mark.asyncio
async def test_call_plugin_tool_honors_base_url_override(ai_mod, monkeypatch):
    fake_client = _FakeAsyncClient(post_response=_FakeResponse({"answer": "42"}))
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    await ai_mod._call_plugin_tool(
        {"endpoint": "/v1/pipeline/pipe-1/query", "base_url": "http://rag:8004"},
        json_body={"question": "what is it"},
    )

    url, _kwargs = fake_client.post_calls[0]
    assert url == "http://rag:8004/v1/pipeline/pipe-1/query"


@pytest.mark.asyncio
async def test_call_plugin_tool_narrows_to_result_field(ai_mod, monkeypatch):
    fake_client = _FakeAsyncClient(
        post_response=_FakeResponse(
            {"answer": "the answer", "sources": ["a", "b"], "confidence": 0.9}
        )
    )
    _patch_httpx(monkeypatch, ai_mod, fake_client)

    result = await ai_mod._call_plugin_tool(
        {"endpoint": "/v1/pipeline/pipe-1/query", "result_field": "answer"},
        json_body={"question": "what is it"},
    )

    assert result == {"answer": "the answer"}


# --- execute_function: RAG-pipeline tool dispatch + stale-pipeline errors ---


@pytest.mark.asyncio
async def test_execute_function_dispatches_a_pipeline_ask_tool(ai_mod, monkeypatch):
    captured = {}

    async def fake_get_tool_definitions():
        return {
            "tools": [
                {
                    "function": {"name": "ask_docs"},
                    "metadata": {
                        "endpoint": "/v1/pipeline/pipe-1/query",
                        "method": "POST",
                        "base_url": "http://rag:8004",
                        "result_field": "answer",
                        "kind": "rag_pipeline",
                    },
                }
            ]
        }

    async def fake_call_plugin_tool(metadata, *, json_body=None, **kwargs):
        captured["metadata"] = metadata
        captured["json_body"] = json_body
        return {"answer": "42"}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)

    result = await ai_mod.execute_function(
        "ask_docs", _FakeRequest(json_body={"question": "what is the answer"})
    )

    assert captured["json_body"] == {"question": "what is the answer"}
    assert captured["metadata"]["base_url"] == "http://rag:8004"
    assert result["result"] == {"answer": "42"}


@pytest.mark.asyncio
async def test_execute_function_surfaces_a_clean_error_for_a_stale_pipeline(
    ai_mod, monkeypatch
):
    """A pipeline deleted/renamed since the last cache refresh 404s downstream
    on rag-pipeline -- this must reach the caller as a clean 404, not an
    unhandled httpx.HTTPStatusError bubbling into a raw 500 (execute_function
    had no error handling at all before this)."""

    async def fake_get_tool_definitions():
        return {
            "tools": [
                {
                    "function": {"name": "ask_docs"},
                    "metadata": {
                        "endpoint": "/v1/pipeline/stale-id/query",
                        "method": "POST",
                        "base_url": "http://rag:8004",
                        "kind": "rag_pipeline",
                    },
                }
            ]
        }

    class _FakeErrResponse:
        status_code = 404
        text = "RAG pipeline not found"

    async def fake_call_plugin_tool(*args, **kwargs):
        raise httpx.HTTPStatusError("404", request=None, response=_FakeErrResponse())

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)

    with pytest.raises(HTTPException) as exc_info:
        await ai_mod.execute_function(
            "ask_docs", _FakeRequest(json_body={"question": "x"})
        )
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail
