"""Real E2E coverage for the chat + tool-calling dispatch loop (#318 phase
4/5): api-gateway's `_chat_with_tools` (routes/ai.py) offering plugin tools
to "the model" and executing them against a REAL running plugin-registry,
for both the native `message.tool_calls` shape and the #250 content-embedded-
JSON fallback used by models (e.g. qwen2.5-coder) that don't emit native
tool_calls.

Real Ollama is replaced by the deterministic fake_ollama stub -- we own the
dispatch code, not the model's output quality (see fake_ollama.py's own
docstring). Each scripted `/api/chat` response is queued via
`live_stack.queue_chat_responses([...])`; the loop consumes one queued
response per real `POST /api/chat` round-trip it makes, so the number of
responses actually consumed is itself proof of how many round-trips ran.

`get_tool_definitions()` (ai.py) fetches real tool metadata from a REAL
`GET {plugin_registry}/v1/plugins/ai/tools` call and caches it for the
process's lifetime -- so a tool name only resolves here if the real
plugin-registry actually advertised it, not because the test faked it up.
"""

import httpx
import pytest


@pytest.fixture(scope="module")
def auth_token(live_stack):
    """Register + log in a throwaway user through the REAL gateway (#613:
    chat/completions now requires a valid JWT, same auth_token pattern as
    test_marketplace_flow.py)."""
    username = "e2e-chat-tools-user"
    password = "TestPass123!"
    httpx.post(
        f"{live_stack.gateway_url}/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
        timeout=15.0,
    )
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=15.0,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_plain_chat_without_tools_is_single_passthrough(live_stack, auth_token):
    """minder_tools omitted (default False) -- exactly one real /api/chat
    round-trip, byte-identical passthrough, no tool dispatch at all."""
    live_stack.queue_chat_responses(
        [{"message": {"content": "Hello there."}}],
    )
    resp = httpx.post(
        f"{live_stack.gateway_url}/v1/ai/chat/completions",
        json={
            "model": "llama3.2:latest",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=15.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["content"] == "Hello there."
    # minder_tools omitted -> chat_completions calls _ollama_chat directly,
    # never _chat_with_tools, so the minder_* fields aren't added here at all
    # (this path must stay byte-identical to a raw Ollama response).
    assert "minder_tools_offered" not in body
    assert "minder_tool_calls_made" not in body


def test_native_tool_calls_dispatches_to_real_plugin_registry(live_stack, auth_token):
    """First scripted response carries a native `tool_calls` entry naming a
    REAL tool (get_crypto_price, backed by the real crypto plugin's real
    get_price action). The loop must: fetch real tool defs from
    plugin-registry, execute the real GET /v1/plugins/crypto/actions/get_price
    call, feed the (real or error) tool result back, and make a SECOND real
    /api/chat call -- only reachable by consuming both queued responses."""
    live_stack.queue_chat_responses(
        [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_crypto_price",
                                "arguments": {"coin": "bitcoin"},
                            }
                        }
                    ]
                }
            },
            {"message": {"content": "The price is $42."}},
        ]
    )
    resp = httpx.post(
        f"{live_stack.gateway_url}/v1/ai/chat/completions",
        json={
            "model": "command-r:latest",
            "messages": [{"role": "user", "content": "price of bitcoin?"}],
            "minder_tools": True,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["content"] == "The price is $42."
    assert body["minder_tools_offered"] is True
    assert body["minder_tool_calls_made"] == 1


def test_content_embedded_tool_call_fallback_dispatches_real_tool(
    live_stack, auth_token
):
    """#250: no native tool_calls, but message.content IS a bare JSON object
    naming a real tool. Only resolves to a tool call because meta_by_name was
    populated from a REAL plugin-registry response -- a strong structural
    signal this isn't faked (see the negative case below)."""
    live_stack.queue_chat_responses(
        [
            {
                "message": {
                    "content": (
                        '{"name": "get_crypto_price", '
                        '"arguments": {"coin": "bitcoin"}}'
                    )
                }
            },
            {"message": {"content": "Bitcoin is currently $42."}},
        ]
    )
    resp = httpx.post(
        f"{live_stack.gateway_url}/v1/ai/chat/completions",
        json={
            "model": "qwen2.5-coder:latest",
            "messages": [{"role": "user", "content": "price of bitcoin?"}],
            "minder_tools": True,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["content"] == "Bitcoin is currently $42."
    assert body["minder_tools_offered"] is True
    assert body["minder_tool_calls_made"] == 1


def test_content_that_only_looks_like_a_tool_call_is_not_dispatched(
    live_stack, auth_token
):
    """JSON-shaped content naming a tool that plugin-registry never actually
    advertised must NOT be treated as a tool call -- only one real /api/chat
    round-trip happens, and the (single) queued response is returned as-is.
    This is the control for the previous test: it proves meta_by_name is
    populated from real tool names, not accepting anything JSON-shaped."""
    live_stack.queue_chat_responses(
        [{"message": {"content": '{"name": "delete_the_entire_database"}'}}]
    )
    resp = httpx.post(
        f"{live_stack.gateway_url}/v1/ai/chat/completions",
        json={
            "model": "qwen2.5-coder:latest",
            "messages": [{"role": "user", "content": "do something"}],
            "minder_tools": True,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=15.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["content"] == '{"name": "delete_the_entire_database"}'
    # #328 regression guard: tools genuinely offered, but the loop must record
    # that none were ever actually invoked -- not silently indistinguishable
    # from a real tool-backed answer.
    assert body["minder_tools_offered"] is True
    assert body["minder_tool_calls_made"] == 0
