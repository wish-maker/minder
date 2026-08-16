"""Unit tests for api-gateway's core/middleware.py -- request-id/metrics and the
Redis-backed fixed-window rate limiter had zero coverage (35% per `coverage run`,
essentially just imports and function signatures).

api-gateway is a hyphenated service dir; middleware.py imports `from core.clients
import redis_client` and `from config import settings` at module top -- fakes for
both are injected and restored, matching test_gateway_tool_args.py's precedent.
`shared.metrics`/`shared.utils.cors` are real (already on the pytest path via
other tests' `from shared...` imports).
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

_MOD_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "core"
    / "middleware.py"
)


class _FakeRedis:
    """Synchronous redis-py-shaped fake -- middleware.py wraps every call in
    run_in_threadpool, same as the real (sync) redis client."""

    def __init__(self, *, raises=None):
        self._counts = {}
        self._ttls = {}
        self.expire_calls = []
        self._raises = raises

    def incr(self, key):
        if self._raises:
            raise self._raises
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))
        self._ttls[key] = seconds

    def ttl(self, key):
        return self._ttls.get(key, -1)


def _load_middleware(*, rate_limit_enabled=True, rate_limit_per_minute=3, redis=None):
    names = ("config", "core", "core.clients")
    saved = {n: sys.modules.get(n) for n in names}
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(
        CORS_ALLOWED_ORIGINS="*",
        RATE_LIMIT_ENABLED=rate_limit_enabled,
        RATE_LIMIT_PER_MINUTE=rate_limit_per_minute,
    )
    sys.modules["config"] = cfg
    sys.modules["core"] = ModuleType("core")
    fake_clients = ModuleType("core.clients")
    fake_clients.redis_client = redis if redis is not None else _FakeRedis()
    sys.modules["core.clients"] = fake_clients
    try:
        spec = importlib.util.spec_from_file_location(
            "gateway_middleware_uut", _MOD_PATH
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for n, m in saved.items():
            if m is not None:
                sys.modules[n] = m
            else:
                sys.modules.pop(n, None)


def _app(mod):
    app = FastAPI()
    mod.register_middleware(app)

    @app.get("/v1/whoami")
    async def whoami():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return TestClient(app)


class TestClientIp:
    def test_returns_the_connecting_peer_host(self):
        mod = _load_middleware()
        request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"))
        assert mod._client_ip(request) == "10.0.0.5"

    def test_falls_back_to_loopback_when_no_client(self):
        mod = _load_middleware()
        request = SimpleNamespace(client=None)
        assert mod._client_ip(request) == "127.0.0.1"


class TestRequestIdMiddleware:
    def test_adds_request_id_and_timing_headers(self):
        mod = _load_middleware(rate_limit_enabled=False)
        client = _app(mod)
        r = client.get("/v1/whoami")
        assert r.status_code == 200
        assert r.headers.get("X-Request-ID")
        assert r.headers.get("X-Response-Time", "").endswith("ms")

    def test_preserves_a_caller_supplied_request_id(self):
        mod = _load_middleware(rate_limit_enabled=False)
        client = _app(mod)
        r = client.get("/v1/whoami", headers={"X-Request-ID": "caller-supplied-id"})
        assert r.headers["X-Request-ID"] == "caller-supplied-id"


class TestRateLimitMiddleware:
    def test_allows_requests_under_the_limit(self):
        mod = _load_middleware(rate_limit_per_minute=3)
        client = _app(mod)
        for _ in range(3):
            assert client.get("/v1/whoami").status_code == 200

    def test_blocks_requests_over_the_limit_with_429_and_retry_after(self):
        redis = _FakeRedis()
        mod = _load_middleware(rate_limit_per_minute=2, redis=redis)
        client = _app(mod)
        client.get("/v1/whoami")
        client.get("/v1/whoami")
        r = client.get("/v1/whoami")
        assert r.status_code == 429
        assert "Retry-After" in r.headers
        assert "Rate limit exceeded" in r.json()["detail"]

    def test_sets_ttl_only_on_the_first_hit(self):
        redis = _FakeRedis()
        mod = _load_middleware(rate_limit_per_minute=5, redis=redis)
        client = _app(mod)
        client.get("/v1/whoami")
        client.get("/v1/whoami")
        assert len(redis.expire_calls) == 1

    def test_exempt_paths_bypass_rate_limiting_entirely(self):
        redis = _FakeRedis()
        mod = _load_middleware(rate_limit_per_minute=1, redis=redis)
        client = _app(mod)
        for _ in range(5):
            assert client.get("/health").status_code == 200
        # Never even touched the counter for an exempt path.
        assert redis._counts == {}

    def test_fails_open_when_redis_is_unreachable(self):
        redis = _FakeRedis(raises=ConnectionError("redis down"))
        mod = _load_middleware(rate_limit_per_minute=1, redis=redis)
        client = _app(mod)
        # Would 429 immediately at limit=1 if rate limiting were enforced --
        # instead every request must succeed since Redis itself is down.
        for _ in range(3):
            assert client.get("/v1/whoami").status_code == 200

    def test_disabled_rate_limiting_never_blocks(self):
        redis = _FakeRedis()
        mod = _load_middleware(
            rate_limit_enabled=False, rate_limit_per_minute=1, redis=redis
        )
        client = _app(mod)
        for _ in range(5):
            assert client.get("/v1/whoami").status_code == 200
