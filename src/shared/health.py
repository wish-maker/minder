"""Dependency-aware health evaluation shared across Minder services (#141).

This deliberately does **not** impose a response *body* model — a shared
``HealthCheckResponse`` was rejected because every service's ``/health`` carries
service-specific fields (#49). It only computes the aggregate status, HTTP code, and a
per-dependency ``checks`` map from a set of probe callables, mirroring the api-gateway
pattern. Each service keeps its own body dict, merges in ``status``/``checks``, and
returns ``JSONResponse(status_code=...)`` so a critical dependency being down surfaces
as a real 503 instead of a misleading 200.
"""

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class DependencyCheck:
    """One dependency to probe.

    ``probe`` may be sync or async; it signals *unhealthy* by raising (or returning
    ``False``). A ``critical`` dep being down flips the service to 503; a non-critical
    one only marks it ``degraded`` (still 200) so an optional backend outage doesn't
    take the service out of a load balancer.
    """

    name: str
    probe: Callable[[], Union[Any, Awaitable[Any]]]
    critical: bool = True


async def evaluate_dependencies(
    checks: Iterable[DependencyCheck],
) -> Tuple[str, int, Dict[str, str]]:
    """Run each probe and derive ``(status, http_code, checks_map)``.

    - any **critical** dep down  → ``("unhealthy", 503)``
    - only **optional** dep down → ``("degraded", 200)``
    - all healthy                → ``("healthy", 200)``

    A probe never propagates: any exception is captured into the checks map.
    """
    results: Dict[str, str] = {}
    critical_down = False
    optional_down = False

    for dep in checks:
        try:
            outcome = dep.probe()
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if outcome is False:
                raise RuntimeError("probe returned False")
            results[dep.name] = "healthy"
        except Exception as e:  # a health probe must never take the endpoint down
            results[dep.name] = f"unhealthy: {type(e).__name__}: {e}"[:200]
            logger.warning("Health probe %r failed: %s", dep.name, e)
            if dep.critical:
                critical_down = True
            else:
                optional_down = True

    if critical_down:
        return "unhealthy", 503, results
    if optional_down:
        return "degraded", 200, results
    return "healthy", 200, results
