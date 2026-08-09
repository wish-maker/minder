"""Recent container logs over the docker-socket-proxy, for the client's Status
page (#platform-status).

JWT-gated (unlike ``/v1/bundles`` GET, which is open): log output can contain
stack traces or an accidentally-logged secret, so this is treated as sensitive
read access, not a plain list. ``name`` is checked against a fixed allowlist --
the same 8 core services the gateway's ``GET /v1/status`` fans out to -- as
defense-in-depth beyond the docker-socket-proxy's own path-regex restriction;
it is never interpolated into a container name without that check.

Docker's logs API returns a multiplexed stream whenever the container's `Tty`
is false (true for every Minder container -- none set `tty: true` in
docker-compose.yml): each frame is an 8-byte header (1 byte stream type
[1=stdout, 2=stderr], 3 reserved bytes, 4-byte big-endian payload length)
followed by that many payload bytes, repeated for the whole response body.
``httpx``/``docker``-the-package aren't dependencies anywhere in this repo, so
``_demux_docker_log_stream`` hand-rolls the ~15 lines this needs instead of
pulling in a new dependency for it.
"""

import os
import struct

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from shared.auth.jwt_middleware import get_current_user

_DOCKER_TIMEOUT = 10.0


def _docker_base_url() -> str:
    """Base URL for the Docker Engine API via the socket-proxy (`DOCKER_HOST`
    tcp://host:port -> http://host:port). Empty if unset. Duplicated from
    routes/bundles.py's identical helper rather than imported, so this route
    module keeps loading cleanly by path in isolation (tests/unit's
    established pattern for plugin-registry route files)."""
    docker_host = os.environ.get("DOCKER_HOST", "")
    if docker_host.startswith("tcp://"):
        return "http://" + docker_host[len("tcp://") :]
    return ""


# The same 8 core services the gateway's GET /v1/status fans out to --
# defense-in-depth against building an arbitrary container name, on top of the
# docker-socket-proxy's own path-regex allowlist.
_KNOWN_SERVICES = frozenset(
    {
        "api-gateway",
        "plugin-registry",
        "marketplace",
        "plugin-state-manager",
        "rag-pipeline",
        "model-management",
        "tts-stt",
        "graph-rag",
    }
)


def _demux_docker_log_stream(raw: bytes) -> list:
    """Split a Docker multiplexed log stream into `{stream, text}` frames.

    Each frame: 1 byte stream type (1=stdout, 2=stderr) + 3 reserved bytes +
    4-byte big-endian payload length, then that many payload bytes.
    """
    frames = []
    offset = 0
    while offset + 8 <= len(raw):
        stream_type, length = struct.unpack(">BxxxI", raw[offset : offset + 8])
        offset += 8
        chunk = raw[offset : offset + length]
        offset += length
        frames.append(
            {
                "stream": "stderr" if stream_type == 2 else "stdout",
                "text": chunk.decode("utf-8", errors="replace"),
            }
        )
    return frames


def build_containers_router(*, settings) -> APIRouter:
    router = APIRouter(tags=["Containers"])

    @router.get("/v1/containers/{name}/logs")
    async def get_container_logs(
        name: str,
        tail: int = Query(200, ge=1, le=2000),
        current_user: dict = Depends(get_current_user),
    ):
        """Recent stdout/stderr lines for one of the known core services,
        fetched over the docker-socket-proxy (JWT-gated)."""
        if name not in _KNOWN_SERVICES:
            raise HTTPException(status_code=404, detail=f"unknown service: {name!r}")
        base = _docker_base_url()
        if not base:
            raise HTTPException(
                status_code=503,
                detail="docker-socket-proxy unreachable (DOCKER_HOST unset)",
            )
        container_name = f"{settings.CONTAINER_PREFIX}-{name}"
        try:
            async with httpx.AsyncClient(base_url=base, timeout=_DOCKER_TIMEOUT) as c:
                r = await c.get(
                    f"/containers/{container_name}/logs",
                    params={"stdout": "true", "stderr": "true", "tail": tail},
                )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=503, detail=f"docker-socket-proxy error: {e}"
            )
        if r.status_code == 404:
            raise HTTPException(
                status_code=404, detail=f"container not running: {container_name!r}"
            )
        if r.status_code != 200:
            raise HTTPException(
                status_code=502, detail=f"docker-socket-proxy returned {r.status_code}"
            )
        return {"name": name, "lines": _demux_docker_log_stream(r.content)}

    return router
