"""Static admin-UI routes -- self-contained settings pages with no build step.

Each is a single HTML+JS file that calls this gateway's own
already-Traefik-exposed, Authelia-gated proxy routes (routes/proxy.py) and
/v1/auth/* endpoints. Plain FileResponse routes rather than a StaticFiles
mount, since there are only a couple of pages today.
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


@router.get("/model-management", include_in_schema=False)
async def model_management_page() -> FileResponse:
    """Serve the model-management page (static/model_management.html, #421)."""
    return FileResponse(_STATIC_DIR / "model_management.html", media_type="text/html")
