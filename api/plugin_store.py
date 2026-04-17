"""
Plugin Store API Endpoints
GitHub repolarından plugin yönetimi
"""

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from .github_installer import GitHubPluginInstaller
from .plugin_store_security import get_default_security_validator

try:
    from .security import InputSanitizer
except ImportError:
    # Fallback for different import paths
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from api.security import InputSanitizer

from .auth import get_current_user_optional

# Import plugin loader for dynamic loading
try:
    from ..core.plugin_loader import PluginLoader
except ImportError:
    # Fallback for different import paths
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.plugin_loader import PluginLoader

logger = logging.getLogger(__name__)

# Create router - kernel dependency will be set from main.py
router = APIRouter(prefix="/plugins/store", tags=["Plugin Store"])

# Global kernel reference - will be set from main.py
_kernel = None


def set_kernel(kernel):
    """Set kernel reference from main.py"""
    global _kernel
    _kernel = kernel


def get_kernel():
    """Get kernel reference"""
    return _kernel


class PluginInstallRequest(BaseModel):
    repo_url: str = Field(..., min_length=10, max_length=500)
    branch: str = "main"
    version: str = "latest"
    author: Optional[str] = None
    bypass_security: bool = False

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v):
        """Validate and sanitize repository URL"""
        is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False)
        if not is_valid:
            raise ValueError(error_msg)
        return InputSanitizer.sanitize_string(v, max_length=500)

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v):
        """Validate branch name"""
        if v:
            is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
            if not is_valid:
                raise ValueError(error_msg)
            return InputSanitizer.sanitize_string(v, max_length=100)
        return v

    @field_validator("author")
    @classmethod
    def validate_author(cls, v):
        """Validate author name"""
        if v:
            is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
            if not is_valid:
                raise ValueError(error_msg)
            return InputSanitizer.sanitize_string(v, max_length=100)
        return v


class PluginSearchResponse(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    total: int


@router.get("/search")
async def search_plugins(q: str = "", current_user: dict = Depends(get_current_user_optional)) -> PluginSearchResponse:
    """Plugin ara"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_store"):
        raise HTTPException(status_code=503, detail="Plugin store not initialized")

    store = kernel.plugin_store
    results = await store.search_plugins(q)

    return PluginSearchResponse(query=q, results=results, total=len(results))


@router.get("/installed")
async def list_installed_plugins(
    current_user: dict = Depends(get_current_user_optional),
):
    """Kurulu plugin'leri listele"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_store"):
        raise HTTPException(status_code=503, detail="Plugin store not initialized")

    store = kernel.plugin_store
    plugins = await store.list_installed_plugins()

    return {"plugins": plugins, "total": len(plugins)}


@router.get("/installed/{plugin_name}")
async def get_plugin_details(plugin_name: str, current_user: dict = Depends(get_current_user_optional)):
    """Plugin detayını al"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_store"):
        raise HTTPException(status_code=503, detail="Plugin store not initialized")

    store = kernel.plugin_store
    details = await store.get_plugin_info(plugin_name)

    if not details:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_name}")

    return details


@router.post("/install")
async def install_plugin(
    request: PluginInstallRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user_optional),
):
    """Plugin'i GitHub reposundan kur (with security validation)"""
    kernel = get_kernel()

    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    try:
        # Download plugin from GitHub
        installer = GitHubPluginInstaller()
        download_result = await installer.install_plugin(request.repo_url, request.branch)

        plugin_name = download_result["plugin_name"]
        plugin_path = Path(download_result["path"])

        # Security validation (unless bypassed)
        if not request.bypass_security:
            validator = get_default_security_validator()

            author = request.author or "unknown"

            # Validate plugin
            is_valid, errors = validator.validate_plugin(
                plugin_path=plugin_path, plugin_name=plugin_name, author=author
            )

            if not is_valid:
                # Remove plugin if validation failed
                shutil.rmtree(plugin_path, ignore_errors=True)

                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "security_validation_failed",
                        "plugin": plugin_name,
                        "issues": errors,
                    },
                )

            logger.info(f"✅ Plugin security validation passed: {plugin_name}")

        # Load plugin into kernel
        try:
            # Get kernel reference
            kernel = get_kernel()
            if not kernel:
                logger.warning(f"⚠️  Kernel not available, plugin downloaded but not loaded: {plugin_name}")
            else:
                # Create plugin loader
                loader = PluginLoader(
                    {
                        "plugins_path": Path("/app/plugins"),
                        "plugins": {plugin_name: {"enabled": True}},
                    }
                )

                # Load the plugin
                plugin_instance = await loader.load_plugin(plugin_name)

                if plugin_instance:
                    # Register plugin in kernel if it has a registry
                    if hasattr(kernel, "registry"):
                        kernel.registry.register_plugin(plugin_name, plugin_instance)
                        logger.info(f"✅ Plugin loaded into kernel registry: {plugin_name}")
                    else:
                        logger.info(f"✅ Plugin loaded but kernel has no registry: {plugin_name}")
                else:
                    logger.warning(f"⚠️  Plugin download successful but loading failed: {plugin_name}")

        except Exception as e:
            logger.error(f"❌ Error loading plugin {plugin_name} into kernel: {e}")
            # Don't fail installation if loading fails - plugin is downloaded

        return {
            "plugin": plugin_name,
            "status": "installed",
            "path": str(plugin_path),
            "metadata": download_result.get("metadata", {}),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Plugin installation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/uninstall/{plugin_name}")
async def uninstall_plugin(plugin_name: str, current_user: dict = Depends(get_current_user_optional)):
    """Plugin'i kaldır"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_store"):
        raise HTTPException(status_code=503, detail="Plugin store not initialized")

    store = kernel.plugin_store

    try:
        success = await store.uninstall_plugin(plugin_name)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to uninstall plugin")

        return {"plugin": plugin_name, "status": "uninstalled"}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update/{plugin_name}")
async def update_plugin(plugin_name: str, current_user: dict = Depends(get_current_user_optional)):
    """Plugin'i güncelle"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_store"):
        raise HTTPException(status_code=503, detail="Plugin store not initialized")

    store = kernel.plugin_store

    try:
        result = await store.update_plugin(plugin_name)

        # Plugin'i yeniden yükle
        # TODO: Plugin'i reload et

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/updates")
async def check_plugin_updates(
    current_user: dict = Depends(get_current_user_optional),
):
    """Tüm plugin'ler için güncelleme kontrolü"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_store"):
        raise HTTPException(status_code=503, detail="Plugin store not initialized")

    store = kernel.plugin_store
    updates = await store.check_updates()

    return {"updates": updates, "total": len(updates)}


@router.get("/index")
async def get_plugin_index(
    current_user: dict = Depends(get_current_user_optional),
):
    """Plugin index'i al"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_store"):
        raise HTTPException(status_code=503, detail="Plugin store not initialized")

    store = kernel.plugin_store
    index = store.plugin_index

    return {"plugins": index, "total": len(index)}
