"""Bundle control-plane over the shared claim-graph brain (#65 item 2).

- ``GET /v1/bundles`` (read-only): the bundle model — claim map + enable-state +
  per-service active/orphaned.
- ``POST /v1/bundles/{name}/enable|disable`` and ``POST /v1/bundles/reconcile``
  (JWT-gated, PR2): persist intent to ``bundles.state.json`` (the SAME secret-free
  file the host CLI writes) and orchestrate containers via the least-privilege
  **docker-socket-proxy** (`DOCKER_HOST`, start/stop only — never create).

Both front-ends (host CLI + this API) compute over the SAME pure ``shared.bundle_graph``
brain. The proxy cannot *create* containers by design (create-with-host-mount would be
host takeover), so a claimed service that was never materialised (e.g. enabling a bundle
that has been off since install) is reported as ``pending_create`` — it comes up on the
next host ``setup.sh start``/``restart`` converge, which has full compose access. This is
the GitOps model in ``docs/architecture/bundles.md``: the API sets desired state; a
privileged host reconciler materialises anything new.
"""

import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException

from shared.auth.jwt_middleware import get_current_user
from shared.bundle_graph import ClaimGraph, parse_bundle_labels, parse_state

CORE_BUNDLE = "core"
_DOCKER_TIMEOUT = 10.0


def _docker_base_url() -> str:
    """Base URL for the Docker Engine API via the socket-proxy (`DOCKER_HOST`
    tcp://host:port → http://host:port). Empty if unset (no orchestration possible)."""
    docker_host = os.environ.get("DOCKER_HOST", "")
    if docker_host.startswith("tcp://"):
        return "http://" + docker_host[len("tcp://") :]
    return ""


class _ContainerOps:
    """Start/stop/inspect a service's container by name over the socket-proxy. Only
    the three verbs the proxy allowlists are used — never create. Each returns a
    short outcome string so the endpoints can report exactly what changed."""

    def __init__(self, base_url: str, prefix: str, timeout: float = _DOCKER_TIMEOUT):
        self._base_url = base_url
        self._prefix = prefix
        self._timeout = timeout

    def _cname(self, service: str) -> str:
        return f"{self._prefix}-{service}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)

    async def _post(self, service: str, verb: str) -> str:
        # Docker: 204 changed, 304 already in that state, 404 no such container.
        try:
            async with self._client() as c:
                r = await c.post(f"/containers/{self._cname(service)}/{verb}")
        except httpx.HTTPError:
            return "error"
        if r.status_code == 204:
            return "changed"
        if r.status_code == 304:
            return "already"
        if r.status_code == 404:
            return "absent"
        return "error"

    async def start(self, service: str) -> str:
        return await self._post(service, "start")

    async def stop(self, service: str) -> str:
        return await self._post(service, "stop")


def build_bundles_router(*, settings, logger, container_ops=None) -> APIRouter:
    router = APIRouter(tags=["Bundles"])

    def _ops() -> "_ContainerOps | None":
        if container_ops is not None:  # test injection
            return container_ops
        base = _docker_base_url()
        if not base:
            return None
        return _ContainerOps(base, settings.CONTAINER_PREFIX)

    def _load() -> "tuple[dict, dict]":
        """Read the claim map (compose labels) + the enable-state, or 503."""
        try:
            compose_text = Path(settings.BUNDLES_COMPOSE_PATH).read_text(
                encoding="utf-8"
            )
        except OSError as e:
            raise HTTPException(
                status_code=503,
                detail=f"bundle map unavailable: cannot read compose file ({e})",
            )
        claims = parse_bundle_labels(compose_text)
        if CORE_BUNDLE not in claims:
            raise HTTPException(
                status_code=503,
                detail="bundle map empty: compose file has no minder.bundle= labels",
            )
        try:
            state = parse_state(
                Path(settings.BUNDLES_STATE_PATH).read_text(encoding="utf-8")
            )
        except OSError:
            state = {}  # absent/unreadable → everything enabled (documented default)
        return claims, state

    def _write_state(state: dict) -> None:
        try:
            Path(settings.BUNDLES_STATE_PATH).write_text(
                json.dumps(state, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as e:
            raise HTTPException(
                status_code=503,
                detail=f"cannot persist bundle state (is bundles.state.json mounted "
                f"read-write?): {e}",
            )

    def _known_bundle(name: str, claims: dict) -> None:
        if name not in claims:
            raise HTTPException(status_code=404, detail=f"unknown bundle: {name!r}")

    @router.get("/v1/bundles")
    async def list_bundles():
        """List every bundle with its enabled state, claimed services, and per-service
        active/orphaned status. Read-only (#65 item 2)."""
        claims, state = _load()
        graph = ClaimGraph(claims, state, CORE_BUNDLE)
        enabled = graph.enabled_bundles()
        bundles = [
            {
                "name": name,
                "core": name == CORE_BUNDLE,
                "enabled": graph.is_enabled(name),
                "claims": list(svcs),
                "services": [
                    {
                        "name": svc,
                        "active": graph.service_active(svc),
                        "claimants": sorted(graph.claimants(svc, enabled)),
                    }
                    for svc in svcs
                ],
            }
            for name, svcs in claims.items()
        ]
        return {
            "bundles": bundles,
            "orphaned": graph.orphaned_services(),
            "count": len(bundles),
        }

    async def _apply(ops, services, verb: str) -> dict:
        """Run start/stop over `services`, bucketing outcomes. `pending_create` (a
        service the proxy reports absent) needs the privileged host converge."""
        out: dict = {"changed": [], "already": [], "pending_create": [], "error": []}
        if ops is None:
            # No proxy reachable → intent persisted but nothing orchestrated live.
            out["pending_create"] = sorted(services)
            return out
        for svc in sorted(services):
            res = await (ops.start(svc) if verb == "start" else ops.stop(svc))
            bucket = "pending_create" if res == "absent" else res
            out.setdefault(bucket, []).append(svc)
        return out

    @router.post("/v1/bundles/{name}/enable")
    async def enable_bundle(name: str, current_user: dict = Depends(get_current_user)):
        """Enable a bundle: persist intent, then START its claimed services that exist.
        Services never materialised come up on the next host start/restart converge
        (reported as ``pending_create``). JWT-gated (#65 item 2, PR2)."""
        claims, state = _load()
        _known_bundle(name, claims)
        state[name] = {"enabled": True}
        _write_state(state)
        graph = ClaimGraph(claims, state, CORE_BUNDLE)
        targets = [s for s in claims[name] if graph.service_active(s)]
        result = await _apply(_ops(), targets, "start")
        logger.info("bundle %s enabled by %s", name, current_user.get("sub", "?"))
        return {
            "bundle": name,
            "enabled": True,
            "started": result["changed"],
            "already_running": result["already"],
            "pending_create": result["pending_create"],
            "errors": result["error"],
        }

    @router.post("/v1/bundles/{name}/disable")
    async def disable_bundle(name: str, current_user: dict = Depends(get_current_user)):
        """Disable a bundle: persist intent, then STOP the services it was keeping alive
        that no other enabled bundle claims (orphans). ``core`` cannot be disabled.
        JWT-gated (#65 item 2, PR2)."""
        if name == CORE_BUNDLE:
            raise HTTPException(status_code=409, detail="core is the always-on kernel")
        claims, state = _load()
        _known_bundle(name, claims)
        # Orphans are computed on the pre-disable graph (services of `name` no OTHER
        # enabled bundle claims), then intent is persisted.
        graph = ClaimGraph(claims, state, CORE_BUNDLE)
        orphans = graph.orphans_after(name)
        state[name] = {"enabled": False}
        _write_state(state)
        result = await _apply(_ops(), orphans, "stop")
        logger.info("bundle %s disabled by %s", name, current_user.get("sub", "?"))
        return {
            "bundle": name,
            "enabled": False,
            "orphaned": orphans,
            "stopped": result["changed"],
            "already_stopped": result["already"],
            "absent": result["pending_create"],
            "errors": result["error"],
        }

    @router.post("/v1/bundles/reconcile")
    async def reconcile_bundles(current_user: dict = Depends(get_current_user)):
        """Converge the running set to the enabled bundles: START every active service
        and STOP every orphan. JWT-gated (#65 item 2, PR2)."""
        claims, state = _load()
        graph = ClaimGraph(claims, state, CORE_BUNDLE)
        all_services = {s for svcs in claims.values() for s in svcs}
        active = [s for s in all_services if graph.service_active(s)]
        orphans = graph.orphaned_services()
        ops = _ops()
        started = await _apply(ops, active, "start")
        stopped = await _apply(ops, orphans, "stop")
        logger.info("bundles reconciled by %s", current_user.get("sub", "?"))
        return {
            "started": started["changed"],
            "already_running": started["already"],
            "pending_create": started["pending_create"],
            "stopped": stopped["changed"],
            "already_stopped": stopped["already"],
            "errors": started["error"] + stopped["error"],
        }

    return router
