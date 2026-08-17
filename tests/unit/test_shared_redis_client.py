"""Unit tests for shared/utils/redis_client.py's create_redis_client(_from_settings).

This factory backs every service's Redis client construction, but had no
dedicated test of its own -- only ever exercised indirectly through other
services' fakes. The ping-success log line and the connection-failure
except/re-raise branch had zero coverage; `redis.Redis` is monkeypatched at
the module level (`redis_client.redis.Redis`) so no real Redis server is
needed to exercise them.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import shared.utils.redis_client as redis_client


class _FakeRedis:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.ping = MagicMock(return_value=True)


def test_create_redis_client_pings_by_default_and_returns_client(monkeypatch):
    monkeypatch.setattr(redis_client.redis, "Redis", _FakeRedis)

    client = redis_client.create_redis_client(
        host="redis-host", port=1234, password="secret", db=2
    )

    assert isinstance(client, _FakeRedis)
    assert client.kwargs == {
        "host": "redis-host",
        "port": 1234,
        "password": "secret",
        "decode_responses": True,
        "db": 2,
    }
    client.ping.assert_called_once()


def test_create_redis_client_skips_ping_when_disabled(monkeypatch):
    monkeypatch.setattr(redis_client.redis, "Redis", _FakeRedis)

    client = redis_client.create_redis_client(host="redis-host", ping=False)

    client.ping.assert_not_called()


def test_create_redis_client_raises_on_ping_failure(monkeypatch):
    class _RaisingRedis(_FakeRedis):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.ping = MagicMock(side_effect=ConnectionError("connection refused"))

    monkeypatch.setattr(redis_client.redis, "Redis", _RaisingRedis)

    with pytest.raises(ConnectionError, match="connection refused"):
        redis_client.create_redis_client(host="redis-host")


def test_create_redis_client_raises_when_construction_itself_fails(monkeypatch):
    def _boom(**kwargs):
        raise ValueError("bad config")

    monkeypatch.setattr(redis_client.redis, "Redis", _boom)

    with pytest.raises(ValueError, match="bad config"):
        redis_client.create_redis_client(host="redis-host")


def test_create_redis_client_from_settings_reads_attributes(monkeypatch):
    monkeypatch.setattr(redis_client.redis, "Redis", _FakeRedis)
    settings = SimpleNamespace(
        REDIS_HOST="settings-host", REDIS_PORT=9999, REDIS_PASSWORD="pw"
    )

    client = redis_client.create_redis_client_from_settings(settings, ping=False)

    assert client.kwargs == {
        "host": "settings-host",
        "port": 9999,
        "password": "pw",
        "decode_responses": True,
        "db": 0,
    }
    client.ping.assert_not_called()


def test_create_redis_client_from_settings_defaults_when_attrs_missing(monkeypatch):
    monkeypatch.setattr(redis_client.redis, "Redis", _FakeRedis)
    settings = SimpleNamespace()  # no REDIS_* attributes at all

    client = redis_client.create_redis_client_from_settings(settings, ping=False)

    assert client.kwargs["host"] == "localhost"
    assert client.kwargs["port"] == 6379
    assert client.kwargs["password"] is None
