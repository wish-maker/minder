"""Unit tests for the shared dependency-aware health evaluator (#141).

Guards the status/HTTP-code derivation every service's /health now relies on: a
critical dep down must yield 503, an optional dep down only 'degraded' (200), and a
probe must never propagate its exception out of the endpoint.
"""

import pytest

from shared.health import DependencyCheck, evaluate_dependencies


async def _ok():
    return None


async def _boom():
    raise RuntimeError("down")


def _sync_ok():
    return None


def _sync_false():
    return False


@pytest.mark.asyncio
async def test_all_healthy_is_200():
    status, code, checks = await evaluate_dependencies(
        [DependencyCheck("pg", _ok), DependencyCheck("redis", _sync_ok)]
    )
    assert (status, code) == ("healthy", 200)
    assert checks == {"pg": "healthy", "redis": "healthy"}


@pytest.mark.asyncio
async def test_critical_down_is_503():
    status, code, checks = await evaluate_dependencies(
        [DependencyCheck("pg", _boom, critical=True)]
    )
    assert (status, code) == ("unhealthy", 503)
    assert checks["pg"].startswith("unhealthy:")


@pytest.mark.asyncio
async def test_optional_down_is_degraded_200():
    status, code, checks = await evaluate_dependencies(
        [DependencyCheck("ollama", _boom, critical=False)]
    )
    assert (status, code) == ("degraded", 200)


@pytest.mark.asyncio
async def test_probe_returning_false_is_unhealthy():
    status, code, checks = await evaluate_dependencies(
        [DependencyCheck("x", _sync_false, critical=True)]
    )
    assert (status, code) == ("unhealthy", 503)


@pytest.mark.asyncio
async def test_critical_wins_over_optional():
    # One optional down + one critical down → the critical one dictates 503.
    status, code, _ = await evaluate_dependencies(
        [
            DependencyCheck("cache", _boom, critical=False),
            DependencyCheck("db", _boom, critical=True),
        ]
    )
    assert (status, code) == ("unhealthy", 503)


@pytest.mark.asyncio
async def test_empty_checks_is_healthy():
    status, code, checks = await evaluate_dependencies([])
    assert (status, code) == ("healthy", 200)
    assert checks == {}
