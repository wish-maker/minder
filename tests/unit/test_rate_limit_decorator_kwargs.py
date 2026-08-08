"""Unit tests for `enforce_rate_limit` actually finding its Request object.

FastAPI's request handler calls an endpoint with EVERY resolved parameter as a
KEYWORD argument (`dependant.call(**values)` in fastapi.routing's
run_endpoint_function) -- never positionally. `enforce_rate_limit`'s wrapper
used to only scan `*args` for a `Request` instance, so in every real request
it silently found nothing and skipped rate limiting entirely -- a no-op
that had gone unnoticed because this decorator had zero test coverage despite
being applied to 4+ endpoints across two services. Fixed to also scan
`kwargs.values()`; these tests call the decorated function exactly the way
FastAPI does (all-keyword) to lock the real-world behavior, not just the
positional-call shape a naive test would use.
"""

import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import Headers
from starlette.types import Scope

from shared.auth.jwt_middleware import _rate_limit_store, enforce_rate_limit


def _fake_request(path: str = "/test", client_host: str = "1.2.3.4") -> Request:
    scope: Scope = {
        "type": "http",
        "path": path,
        "headers": Headers({}).raw,
        "client": (client_host, 12345),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clear_rate_limit_store():
    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()


@pytest.mark.asyncio
async def test_finds_request_passed_as_keyword_like_fastapi_does():
    """The exact real-world call shape: every param passed by keyword."""

    @enforce_rate_limit(max_requests=2, window_minutes=1)
    async def handler(*, body: dict, request: Request):
        return "ok"

    req = _fake_request()
    assert await handler(body={}, request=req) == "ok"
    assert await handler(body={}, request=req) == "ok"
    with pytest.raises(HTTPException) as exc_info:
        await handler(body={}, request=req)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_still_finds_request_passed_positionally():
    """Backward-compatible: a positional Request (if ever called that way)
    must still be found, not just kwargs."""

    @enforce_rate_limit(max_requests=1, window_minutes=1)
    async def handler(request: Request):
        return "ok"

    req = _fake_request(path="/other")
    assert await handler(req) == "ok"
    with pytest.raises(HTTPException):
        await handler(req)


@pytest.mark.asyncio
async def test_no_request_anywhere_skips_rate_limiting():
    """No Request in args or kwargs -- falls through unrestricted, matching
    the documented "skip rate limiting" fallback."""

    @enforce_rate_limit(max_requests=1, window_minutes=1)
    async def handler(*, body: dict):
        return "ok"

    for _ in range(5):
        assert await handler(body={}) == "ok"


@pytest.mark.asyncio
async def test_limit_is_keyed_per_path_not_global():
    """Two different request paths for the same client must not share a
    rate-limit bucket."""

    @enforce_rate_limit(max_requests=1, window_minutes=1)
    async def handler(*, request: Request):
        return "ok"

    assert await handler(request=_fake_request(path="/a")) == "ok"
    assert await handler(request=_fake_request(path="/b")) == "ok"
    with pytest.raises(HTTPException):
        await handler(request=_fake_request(path="/a"))
