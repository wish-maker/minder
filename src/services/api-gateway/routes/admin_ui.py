"""Static admin-UI routes -- currently just the plugin-config settings page.

No build step / SPA framework: a single self-contained HTML+JS file that calls
this gateway's own already-Traefik-exposed, Authelia-gated /v1/plugins/*/config
proxy (routes/proxy.py) and /v1/auth/* endpoints. A plain FileResponse route
rather than a StaticFiles mount, since there's exactly one page today.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/plugin-config", include_in_schema=False)
async def plugin_config_page() -> FileResponse:
    """Serve the plugin-configuration settings page (static/plugin_config.html)."""
    return FileResponse(_STATIC_DIR / "plugin_config.html", media_type="text/html")
