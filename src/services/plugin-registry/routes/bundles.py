"""Read-only bundle view for API consumers (#65 item 2).

Reports the bundle model — the Compose-label-derived claim map + the enable-state +
which services are active/orphaned — using the SAME pure brain the host CLI uses
(``shared.bundle_graph``). Read-only: **no orchestration** (enable/disable/reconcile
need the docker-socket-proxy, which is coupled with the Pi deploy #8).

The compose file (bundle-map source of truth via ``minder.bundle=`` labels) and the
secret-free ``bundles.state.json`` are mounted read-only. An absent state file means
everything is enabled (the documented default).
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from shared.bundle_graph import ClaimGraph, parse_bundle_labels, parse_state

CORE_BUNDLE = "core"


def build_bundles_router(*, settings, logger) -> APIRouter:
    router = APIRouter(tags=["Bundles"])

    def _load() -> "tuple[dict, dict]":
        """Read the claim map (from the compose labels) + the enable-state, or 503."""
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

    return router
