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

from .auth import get_current_user_optional
from .github_installer import GitHubPluginInstaller
from .plugin_store_security import get_default_security_validator

# Initialize logger at module level
logger = logging.getLogger(__name__)

# Import manifest validator
try:
    from ..core.plugin_manifest import validate_plugin_for_installation  # noqa: F401
except ImportError:
    # Fallback for different import paths
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from .security import InputSanitizer
except ImportError:
    # Fallback for different import paths
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from api.security import InputSanitizer

# Import plugin loader for dynamic loading
try:
    from ..core.plugin_loader import PluginLoader  # noqa: F401
except ImportError:
    # Fallback for different import paths
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.plugin_loader import PluginLoader  # noqa: F401

# Import sandbox and security features
try:
    from ..core.plugin_hot_reload import PluginReloader
    from ..core.plugin_observability import PluginHealthMonitor, PluginMetrics
    from ..core.plugin_permissions import PermissionEnforcer, SandboxedPlugin
    from ..core.plugin_sandbox import SandboxedPluginLoader, SubprocessSandbox
except ImportError:
    # Fallback for different import paths
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    # Only import if modules actually exist
    try:
        from core.plugin_sandbox import SandboxedPluginLoader, SubprocessSandbox

        SANDBOX_AVAILABLE = True
    except ImportError:
        SANDBOX_AVAILABLE = False
        SandboxedPluginLoader = None
        SubprocessSandbox = None
        logger.warning("Plugin sandbox not available - using regular loader")

    try:
        from core.plugin_permissions import PermissionEnforcer, SandboxedPlugin

        PERMISSIONS_AVAILABLE = True
    except ImportError:
        PERMISSIONS_AVAILABLE = False
        SandboxedPlugin = None
        PermissionEnforcer = None
        logger.warning("Plugin permissions not available")

    try:
        from core.plugin_hot_reload import PluginReloader

        HOT_RELOAD_AVAILABLE = True
    except ImportError:
        HOT_RELOAD_AVAILABLE = False
        PluginReloader = None
        logger.warning("Plugin hot reload not available")

    try:
        from core.plugin_observability import PluginHealthMonitor, PluginMetrics

        OBSERVABILITY_AVAILABLE = True
    except ImportError:
        OBSERVABILITY_AVAILABLE = False
        PluginMetrics = None
        PluginHealthMonitor = None
        logger.warning("Plugin observability not available")

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

        # Step 1: MANDATORY manifest validation
        from .plugin_store_security import validate_plugin_for_installation as validate_security

        manifest_valid, manifest, manifest_errors = validate_security(plugin_path)

        if not manifest_valid:
            # Remove plugin if manifest validation failed
            shutil.rmtree(plugin_path, ignore_errors=True)

            raise HTTPException(
                status_code=400,
                detail={
                    "error": "manifest_validation_failed",
                    "plugin": plugin_name,
                    "issues": manifest_errors,
                },
            )

        logger.info(f"✅ Plugin manifest validation passed: {plugin_name}")

        # Step 2: MANDATORY security validation (NO BYPASS POSSIBLE)
        validator = get_default_security_validator()

        author = request.author or "unknown"

        # Validate plugin security
        is_valid, errors = validator.validate_plugin(plugin_path=plugin_path, plugin_name=plugin_name, author=author)

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

        # Step 3: Load plugin with SANDBOX and PERMISSION ENFORCEMENT
        try:
            # Get kernel reference
            kernel = get_kernel()
            if not kernel:
                logger.warning(f"⚠️  Kernel not available, plugin downloaded but not loaded: {plugin_name}")
            else:
                # Use SANDBOXED plugin loader (not regular loader)
                sandboxed_loader = SandboxedPluginLoader()

                # Load plugin with sandbox (untrusted = use subprocess)
                # In production, you'd check if plugin is trusted
                sandbox = await sandboxed_loader.load_plugin(
                    plugin_path, trusted=False  # ← Untrusted plugins use subprocess isolation
                )

                logger.info(f"✅ Plugin loaded in sandbox: {plugin_name}")

                # Store sandbox reference for later use
                if not hasattr(kernel, "plugin_sandboxes"):
                    kernel.plugin_sandboxes = {}
                kernel.plugin_sandboxes[plugin_name] = sandbox

        except Exception as e:
            logger.error(f"❌ Error loading plugin {plugin_name} into sandbox: {e}")
            # Don't fail installation if loading fails - plugin is downloaded and validated

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


# ============================================================================
# NEW: Observability & Monitoring Endpoints
# ============================================================================


@router.get("/health/{plugin_name}")
async def get_plugin_health(plugin_name: str, current_user: dict = Depends(get_current_user_optional)):
    """Get plugin health status"""
    kernel = get_kernel()

    if not kernel:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    try:
        plugin = await kernel.registry.get_plugin(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_name}")

        # Get plugin metadata
        metadata = kernel.registry.metadata.get(plugin_name)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Plugin metadata not found: {plugin_name}")

        return {
            "plugin": plugin_name,
            "status": plugin.status.value,
            "healthy": plugin.status.value == "ready",
            "version": metadata.version,
            "description": metadata.description,
            "capabilities": metadata.capabilities,
            "author": metadata.author,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed for {plugin_name}: {e}")
        return {"plugin": plugin_name, "status": "unhealthy", "healthy": False, "error": str(e)}


@router.get("/health")
async def get_all_plugin_health(current_user: dict = Depends(get_current_user_optional)):
    """Get health status of all plugins"""
    kernel = get_kernel()

    if not kernel:
        return {"plugins": {}, "total": 0, "error": "Kernel not initialized"}

    try:
        plugins = await kernel.registry.list_plugins()
        return {"plugins": {p["name"]: p for p in plugins}, "total": len(plugins)}
    except Exception as e:
        logger.error(f"Error getting plugin health: {e}", exc_info=True)
        return {"plugins": {}, "total": 0, "error": str(e)}


@router.post("/reload/{plugin_name}")
async def reload_plugin(
    plugin_name: str,
    strategy: str = "hot-swap",
    preserve_state: bool = True,
    current_user: dict = Depends(get_current_user_optional),
):
    """Reload plugin without restart"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_sandboxes"):
        raise HTTPException(status_code=503, detail="Plugin sandboxes not initialized")

    # Create reloader
    reloader = PluginReloader(kernel.plugin_sandboxes.get(plugin_name))

    try:
        result = await reloader.reload_plugin(plugin_name, strategy=strategy, preserve_state=preserve_state)

        return result

    except Exception as e:
        logger.error(f"Failed to reload {plugin_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{plugin_name}")
async def get_plugin_metrics(plugin_name: str, current_user: dict = Depends(get_current_user_optional)):
    """Get plugin performance metrics"""
    kernel = get_kernel()

    if not kernel or not hasattr(kernel, "plugin_sandboxes"):
        raise HTTPException(status_code=503, detail="Plugin sandboxes not initialized")

    sandbox = kernel.plugin_sandboxes.get(plugin_name)

    if not sandbox:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_name}")

    # Get metrics from sandbox
    # (This would require implementing metrics collection in sandbox)
    return {
        "plugin": plugin_name,
        "message": "Metrics collection not yet implemented",
        "status": "TODO",
    }


# ============================================================================
# Helper function to initialize observability in main.py
# ============================================================================


async def initialize_plugin_observability(kernel):
    """Initialize plugin observability system"""
    try:
        # Create metrics and health monitor
        metrics = PluginMetrics()
        health_monitor = PluginHealthMonitor(metrics)

        # Store in kernel for later use
        kernel.plugin_metrics = metrics
        kernel.plugin_health_monitor = health_monitor

        logger.info("✅ Plugin observability initialized")

    except Exception as e:
        logger.error(f"❌ Failed to initialize observability: {e}")
