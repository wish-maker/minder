"""Unit tests for api-gateway's Authelia OIDC client (core/oidc.py, #<issue>).

Shipped with zero automated coverage originally -- every assertion here was
verified manually against a real Authelia instance during development (see
the module's own docstrings), but nothing guarded against a regression.

api-gateway is a hyphenated service dir; oidc.py imports ``from config import
settings`` at module top -- a fake config is injected and restored, matching
test_gateway_tool_args.py's pattern. httpx.AsyncClient and jose's jwk/jwt are
swapped for fakes so no real network call or real signature check happens.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

_OIDC_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "core"
    / "oidc.py"
)


@pytest.fixture
def oidc_mod():
    saved_config = sys.modules.get("config")
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(
        AUTHELIA_ISSUER_URL="https://authelia.minder.local",
        AUTHELIA_INTERNAL_URL="http://minder-authelia:9091",
        MINDER_OIDC_CLIENT_ID="minder-client",
        MINDER_OIDC_CLIENT_SECRET="test-client-secret",
        MINDER_OIDC_REDIRECT_URI="https://api.minder.local/v1/auth/oidc/callback",
    )
    sys.modules["config"] = cfg
    try:
        spec = importlib.util.spec_from_file_location("oidc_under_test", _OIDC_MOD)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    """Stands in for every ``httpx.AsyncClient(...)`` instantiation in the
    module under test -- each call site opens its own client via a fresh
    ``async with``, but the factory below always hands back this same
    instance, so responses are consumed strictly in call order."""

    def __init__(self, get_responses=None, post_responses=None):
        self._get_responses = list(get_responses or [])
        self._post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        self.get_calls.append((url, headers))
        return self._get_responses.pop(0)

    async def post(self, url, headers=None, auth=None, data=None):
        self.post_calls.append((url, headers, auth, data))
        return self._post_responses.pop(0)


def _install_fake_client(oidc_mod, monkeypatch, fake_client):
    monkeypatch.setattr(oidc_mod.httpx, "AsyncClient", lambda *a, **kw: fake_client)


# ── _internalize ────────────────────────────────────────────────────────────


def test_internalize_rewrites_public_host_to_internal(oidc_mod):
    out = oidc_mod._internalize("https://authelia.minder.local/api/oidc/token")
    assert out == "http://minder-authelia:9091/api/oidc/token"


# ── exchange_code_for_tokens ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_success(oidc_mod, monkeypatch):
    discovery = _FakeResponse(
        200, {"token_endpoint": "https://authelia.minder.local/api/oidc/token"}
    )
    token_resp = _FakeResponse(200, {"id_token": "idtok", "access_token": "acctok"})
    client = _FakeAsyncClient(get_responses=[discovery], post_responses=[token_resp])
    _install_fake_client(oidc_mod, monkeypatch, client)

    result = await oidc_mod.exchange_code_for_tokens("authcode")

    assert result == {"id_token": "idtok", "access_token": "acctok"}
    post_url, _headers, auth, data = client.post_calls[0]
    assert post_url == "http://minder-authelia:9091/api/oidc/token"
    assert auth == ("minder-client", "test-client-secret")
    assert data == {
        "grant_type": "authorization_code",
        "code": "authcode",
        "redirect_uri": "https://api.minder.local/v1/auth/oidc/callback",
    }


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_non_200_raises_502(oidc_mod, monkeypatch):
    discovery = _FakeResponse(
        200, {"token_endpoint": "https://authelia.minder.local/api/oidc/token"}
    )
    bad_resp = _FakeResponse(400, text="invalid_client")
    client = _FakeAsyncClient(get_responses=[discovery], post_responses=[bad_resp])
    _install_fake_client(oidc_mod, monkeypatch, client)

    with pytest.raises(HTTPException) as exc:
        await oidc_mod.exchange_code_for_tokens("authcode")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_missing_tokens_raises_502(
    oidc_mod, monkeypatch
):
    discovery = _FakeResponse(
        200, {"token_endpoint": "https://authelia.minder.local/api/oidc/token"}
    )
    incomplete_resp = _FakeResponse(200, {"access_token": "acctok"})
    client = _FakeAsyncClient(
        get_responses=[discovery], post_responses=[incomplete_resp]
    )
    _install_fake_client(oidc_mod, monkeypatch, client)

    with pytest.raises(HTTPException) as exc:
        await oidc_mod.exchange_code_for_tokens("authcode")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_discovery_missing_token_endpoint_raises_502(
    oidc_mod, monkeypatch
):
    # A malformed/incomplete discovery document (e.g. Authelia returning an
    # unexpected shape) used to raise a bare KeyError here instead of the same
    # clean 502 every other malformed-response case in this module gets.
    discovery = _FakeResponse(200, {})  # no token_endpoint key at all
    client = _FakeAsyncClient(get_responses=[discovery])
    _install_fake_client(oidc_mod, monkeypatch, client)

    with pytest.raises(HTTPException) as exc:
        await oidc_mod.exchange_code_for_tokens("authcode")
    assert exc.value.status_code == 502
    assert "token_endpoint" in exc.value.detail


# ── verify_id_token ──────────────────────────────────────────────────────────


def _discovery_and_jwks(kid="test-kid"):
    discovery = _FakeResponse(
        200, {"jwks_uri": "https://authelia.minder.local/jwks.json"}
    )
    jwks = _FakeResponse(200, {"keys": [{"kid": kid, "kty": "RSA"}]})
    return discovery, jwks


@pytest.mark.asyncio
async def test_verify_id_token_success(oidc_mod, monkeypatch):
    discovery, jwks = _discovery_and_jwks()
    client = _FakeAsyncClient(get_responses=[discovery, jwks])
    _install_fake_client(oidc_mod, monkeypatch, client)
    monkeypatch.setattr(
        oidc_mod,
        "jwt",
        SimpleNamespace(
            get_unverified_header=lambda token: {"kid": "test-kid"},
            decode=lambda *a, **kw: {"sub": "abc-123", "nonce": "expected-nonce"},
        ),
    )
    monkeypatch.setattr(
        oidc_mod, "jwk", SimpleNamespace(construct=lambda k, alg: "pub")
    )

    claims = await oidc_mod.verify_id_token(
        "idtok", "acctok", expected_nonce="expected-nonce"
    )

    assert claims == {"sub": "abc-123", "nonce": "expected-nonce"}


@pytest.mark.asyncio
async def test_verify_id_token_unknown_kid_raises_502(oidc_mod, monkeypatch):
    discovery, jwks = _discovery_and_jwks(kid="other-kid")
    client = _FakeAsyncClient(get_responses=[discovery, jwks])
    _install_fake_client(oidc_mod, monkeypatch, client)
    monkeypatch.setattr(
        oidc_mod,
        "jwt",
        SimpleNamespace(get_unverified_header=lambda token: {"kid": "test-kid"}),
    )

    with pytest.raises(HTTPException) as exc:
        await oidc_mod.verify_id_token("idtok", "acctok", expected_nonce="n")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_verify_id_token_nonce_mismatch_raises_401(oidc_mod, monkeypatch):
    discovery, jwks = _discovery_and_jwks()
    client = _FakeAsyncClient(get_responses=[discovery, jwks])
    _install_fake_client(oidc_mod, monkeypatch, client)
    monkeypatch.setattr(
        oidc_mod,
        "jwt",
        SimpleNamespace(
            get_unverified_header=lambda token: {"kid": "test-kid"},
            decode=lambda *a, **kw: {"sub": "abc-123", "nonce": "wrong-nonce"},
        ),
    )
    monkeypatch.setattr(
        oidc_mod, "jwk", SimpleNamespace(construct=lambda k, alg: "pub")
    )

    with pytest.raises(HTTPException) as exc:
        await oidc_mod.verify_id_token(
            "idtok", "acctok", expected_nonce="expected-nonce"
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_id_token_bad_signature_raises_401(oidc_mod, monkeypatch):
    discovery, jwks = _discovery_and_jwks()
    client = _FakeAsyncClient(get_responses=[discovery, jwks])
    _install_fake_client(oidc_mod, monkeypatch, client)

    def _raise(*a, **kw):
        raise ValueError("signature verification failed")

    monkeypatch.setattr(
        oidc_mod,
        "jwt",
        SimpleNamespace(
            get_unverified_header=lambda token: {"kid": "test-kid"}, decode=_raise
        ),
    )
    monkeypatch.setattr(
        oidc_mod, "jwk", SimpleNamespace(construct=lambda k, alg: "pub")
    )

    with pytest.raises(HTTPException) as exc:
        await oidc_mod.verify_id_token("idtok", "acctok", expected_nonce="n")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_id_token_discovery_missing_jwks_uri_raises_502(
    oidc_mod, monkeypatch
):
    # Same class of malformed-discovery-document gap as
    # test_exchange_code_for_tokens_discovery_missing_token_endpoint_raises_502,
    # for the other _discover() consumer -- used to raise a bare KeyError.
    discovery = _FakeResponse(200, {})  # no jwks_uri key at all
    client = _FakeAsyncClient(get_responses=[discovery])
    _install_fake_client(oidc_mod, monkeypatch, client)

    with pytest.raises(HTTPException) as exc:
        await oidc_mod.verify_id_token("idtok", "acctok", expected_nonce="n")
    assert exc.value.status_code == 502
    assert "jwks_uri" in exc.value.detail


# ── fetch_userinfo ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_userinfo_success(oidc_mod, monkeypatch):
    resp = _FakeResponse(200, {"preferred_username": "alice", "groups": ["admins"]})
    client = _FakeAsyncClient(get_responses=[resp])
    _install_fake_client(oidc_mod, monkeypatch, client)

    result = await oidc_mod.fetch_userinfo("acctok")

    assert result == {"preferred_username": "alice", "groups": ["admins"]}
    url, headers = client.get_calls[0]
    assert headers["Authorization"] == "Bearer acctok"


@pytest.mark.asyncio
async def test_fetch_userinfo_failure_is_best_effort_empty_dict(oidc_mod, monkeypatch):
    resp = _FakeResponse(403, text="forbidden")
    client = _FakeAsyncClient(get_responses=[resp])
    _install_fake_client(oidc_mod, monkeypatch, client)

    result = await oidc_mod.fetch_userinfo("acctok")

    assert result == {}
