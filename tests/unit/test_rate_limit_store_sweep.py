"""Unit tests for the periodic stale-key sweep (#634).

_prune_rate_limit_key only prunes a key when that SAME key is looked up
again -- a key hit exactly once (a one-off request, or an attacker's
scan-then-vanish IP) was never revisited and stayed in _rate_limit_store
forever, growing it unboundedly on a long-running process. _sweep_stale_keys
now drops any key whose newest timestamp is older than
_SWEEP_STALE_AFTER_SECONDS, and enforce_rate_limit's wrapper calls it every
_SWEEP_EVERY_N_CALLS invocations regardless of which keys are being looked up.
"""

import pytest
from fastapi import Request
from starlette.datastructures import Headers
from starlette.types import Scope

import shared.auth.jwt_middleware as jwt_middleware
from shared.auth.jwt_middleware import (
    _rate_limit_store,
    _sweep_stale_keys,
    enforce_rate_limit,
)


def _fake_request(path: str) -> Request:
    scope: Scope = {
        "type": "http",
        "path": path,
        "headers": Headers({}).raw,
        "client": ("9.9.9.9", 12345),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clear_rate_limit_store():
    _rate_limit_store.clear()
    jwt_middleware._calls_since_sweep = 0
    yield
    _rate_limit_store.clear()
    jwt_middleware._calls_since_sweep = 0


def test_sweep_drops_keys_older_than_cutoff():
    _rate_limit_store["stale"] = [100.0]
    _rate_limit_store["fresh"] = [900.0]
    now = 1000.0
    # Use a tight monkeypatched cutoff instead of the real (generous) 3600s
    # window, so the test doesn't need huge numbers.
    jwt_middleware._SWEEP_STALE_AFTER_SECONDS = 500  # cutoff = now - 500 = 500
    try:
        _sweep_stale_keys(_rate_limit_store, now)
    finally:
        jwt_middleware._SWEEP_STALE_AFTER_SECONDS = 3600
    assert "stale" not in _rate_limit_store  # newest ts (100) < cutoff (500)
    assert _rate_limit_store["fresh"] == [900.0]  # newest ts (900) >= cutoff


def test_sweep_ignores_already_empty_lists_by_removing_them():
    _rate_limit_store["empty"] = []
    _sweep_stale_keys(_rate_limit_store, now=1000.0)
    assert "empty" not in _rate_limit_store


@pytest.mark.asyncio
async def test_one_off_keys_are_eventually_swept_by_the_decorator():
    """A flood of single-use keys (the exact scenario in #634 -- e.g. an
    attacker's scan-then-vanish IPs, each hitting a different path once) must
    not grow the store forever: once _SWEEP_EVERY_N_CALLS calls have passed,
    the next call triggers a sweep that drops any of them older than the
    (monkeypatched, tight) staleness cutoff."""
    jwt_middleware._SWEEP_EVERY_N_CALLS = 10
    # -1 => cutoff = now + 1, so every timestamp recorded by an earlier call
    # (always <= that call's own "now") is guaranteed stale regardless of
    # wall-clock resolution -- avoids flakiness from equal/near-equal
    # timestamps on a fast test run.
    jwt_middleware._SWEEP_STALE_AFTER_SECONDS = -1
    try:

        @enforce_rate_limit(max_requests=100, window_minutes=1)
        async def handler(*, request: Request):
            return "ok"

        for i in range(9):
            await handler(request=_fake_request(path=f"/one-off-{i}"))
        assert len(_rate_limit_store) == 9  # not yet swept

        # 10th call: increments the counter to the threshold, sweeps BEFORE
        # recording itself, then records its own key.
        await handler(request=_fake_request(path="/one-off-9"))
        assert len(_rate_limit_store) == 1  # only the just-recorded key survives
    finally:
        jwt_middleware._SWEEP_EVERY_N_CALLS = 500
        jwt_middleware._SWEEP_STALE_AFTER_SECONDS = 3600
