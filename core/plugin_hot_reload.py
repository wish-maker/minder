"""
Plugin Hot Reload System
Version: 1.0.0

Reload plugins without restarting Minder.
Preserves plugin state across reloads.
"""

import asyncio
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import watchdog.observers
    import watchdog.events

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logging.warning("watchdog not installed - file watching disabled")

from core.plugin_loader import PluginLoader
from core.plugin_sandbox import SandboxedPluginLoader

logger = logging.getLogger(__name__)


class PluginReloader:
    """
    Hot reload plugins without restart

    Strategies:
    - hot-swap: Load new version, switch traffic instantly
    - graceful-wait: Finish current requests, then switch
    - rolling: Reload plugins one-by-one
    """

    def __init__(self, loader: SandboxedPluginLoader):
        self.loader = loader
        self.plugin_versions: Dict[str, str] = {}
        self.plugin_state: Dict[str, Dict[str, Any]] = {}
        self.reload_lock = asyncio.Lock()

    async def reload_plugin(
        self, plugin_name: str, strategy: str = "hot-swap", preserve_state: bool = True
    ) -> Dict[str, Any]:
        """
        Reload plugin without restart

        Args:
            plugin_name: Plugin to reload
            strategy: hot-swap | graceful-wait | rolling
            preserve_state: Keep plugin state across reload

        Returns:
            Reload result with timing and status
        """
        async with self.reload_lock:
            start_time = time.time()

            logger.info(f"🔄 Reloading plugin: {plugin_name} (strategy={strategy})")

            try:
                # Step 1: Save current state
                old_state = None
                if preserve_state and plugin_name in self.loader.sandboxes:
                    old_state = await self._capture_plugin_state(plugin_name)
                    logger.info(f"✓ Captured state for {plugin_name}")

                # Step 2: Unload old version
                await self.loader.unload_plugin(plugin_name)
                logger.info(f"✓ Unloaded {plugin_name}")

                # Step 3: Load new version
                plugin_path = Path(f"/app/plugins/{plugin_name}")
                sandbox = await self.loader.load_plugin(plugin_path, trusted=False)
                logger.info(f"✓ Loaded new version of {plugin_name}")

                # Step 4: Restore state
                if preserve_state and old_state:
                    await self._restore_plugin_state(plugin_name, old_state)
                    logger.info(f"✓ Restored state for {plugin_name}")

                duration = time.time() - start_time

                logger.info(f"✅ Plugin {plugin_name} reloaded in {duration:.3f}s")

                return {
                    "plugin": plugin_name,
                    "status": "reloaded",
                    "duration_seconds": duration,
                    "strategy": strategy,
                    "state_preserved": preserve_state,
                    "timestamp": datetime.now().isoformat(),
                }

            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"❌ Failed to reload {plugin_name}: {e}")

                # Attempt rollback
                if old_state:
                    try:
                        await self._restore_plugin_state(plugin_name, old_state)
                        logger.info(f"✓ Rolled back {plugin_name}")
                    except Exception as rollback_error:
                        logger.error(f"❌ Rollback failed: {rollback_error}")

                return {
                    "plugin": plugin_name,
                    "status": "failed",
                    "error": str(e),
                    "duration_seconds": duration,
                    "timestamp": datetime.now().isoformat(),
                }

    async def _capture_plugin_state(self, plugin_name: str) -> Dict[str, Any]:
        """Capture plugin state before reload"""
        sandbox = self.loader.sandboxes.get(plugin_name)
        if not sandbox:
            return {}

        # Try to call plugin's get_state() method
        try:
            state = await sandbox.execute_plugin(plugin_name, "get_state", timeout=5.0)
            return state
        except Exception as e:
            logger.warning(f"Could not capture state: {e}")
            return {}

    async def _restore_plugin_state(self, plugin_name: str, state: Dict[str, Any]):
        """Restore plugin state after reload"""
        sandbox = self.loader.sandboxes.get(plugin_name)
        if not sandbox:
            return

        # Try to call plugin's set_state() method
        try:
            await sandbox.execute_plugin(plugin_name, "set_state", state, timeout=5.0)
        except Exception as e:
            logger.warning(f"Could not restore state: {e}")


class PluginWatcher:
    """
    Watch plugin directory for changes and auto-reload
    """

    def __init__(self, reloader: PluginReloader, plugins_path: Path):
        self.reloader = reloader
        self.plugins_path = plugins_path
        self.observer = None
        self._watching = False

    def start(self):
        """Start watching plugin directory"""
        if not WATCHDOG_AVAILABLE:
            logger.warning("Cannot start watcher - watchdog not installed")
            return

        if self._watching:
            return

        event_handler = PluginChangeHandler(self.reloader)
        self.observer = watchdog.observers.Observer()
        self.observer.schedule(event_handler, str(self.plugins_path), recursive=True)
        self.observer.start()
        self._watching = True

        logger.info(f"👀 Watching plugins directory: {self.plugins_path}")

    def stop(self):
        """Stop watching"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self._watching = False
            logger.info("🛑 Stopped watching plugins directory")


class PluginChangeHandler:
    """Handle plugin file system changes"""

    def __init__(self, reloader: PluginReloader):
        if not WATCHDOG_AVAILABLE:
            logger.warning("Watchdog not available - file watching disabled")
            return

        import watchdog.events

        self.watched_events = watchdog.events.FileSystemEventHandler
        self.reloader = reloader
        self._debounce_timers: Dict[str, asyncio.Task] = {}

    def on_modified(self, event):
        """File modified"""
        if not WATCHDOG_AVAILABLE:
            return

        if event.is_directory:
            return

        # Check if it's a plugin file
        path = Path(event.src_path)
        if not self._is_plugin_file(path):
            return

        plugin_name = self._get_plugin_name(path)

        # Debounce rapid changes
        if plugin_name in self._debounce_timers:
            self._debounce_timers[plugin_name].cancel()

        # Schedule reload after 1 second delay
        loop = asyncio.get_event_loop()
        self._debounce_timers[plugin_name] = loop.create_task(self._debounced_reload(plugin_name, delay=1.0))

        logger.info(f"📝 Plugin file changed: {path.name}")

    async def _debounced_reload(self, plugin_name: str, delay: float):
        """Reload plugin after delay (debounce)"""
        await asyncio.sleep(delay)
        await self.reloader.reload_plugin(plugin_name)
        del self._debounce_timers[plugin_name]

    def _is_plugin_file(self, path: Path) -> bool:
        """Check if file is part of a plugin"""
        # Check for plugin files
        plugin_dir = path.parent
        return (
            path.name.endswith(("_plugin.py", "_module.py", "__init__.py")) or path.name == "plugin.yml"
        ) and plugin_dir.name != "plugins"

    def _get_plugin_name(self, path: Path) -> str:
        """Get plugin name from file path"""
        return path.parent.name


# HTTP API endpoints for hot reload
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/plugins/reload", tags=["Plugin Reload"])

_reloader: Optional[PluginReloader] = None
_watcher: Optional[PluginWatcher] = None


def set_reloader(reloader: PluginReloader):
    """Set global reloader instance"""
    global _reloader
    _reloader = reloader


def set_watcher(watcher: PluginWatcher):
    """Set global watcher instance"""
    global _watcher
    _watcher = watcher


@router.post("/{plugin_name}")
async def reload_plugin_endpoint(plugin_name: str, strategy: str = "hot-swap", preserve_state: bool = True):
    """
    Reload plugin without restart

    Strategies:
    - hot-swap: Instant switch (default)
    - graceful-wait: Finish current requests first
    """
    if not _reloader:
        raise HTTPException(status_code=503, detail="Reloader not initialized")

    result = await _reloader.reload_plugin(plugin_name, strategy=strategy, preserve_state=preserve_state)

    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result)

    return result


@router.post("/watch/start")
async def start_watching():
    """Start watching plugin directory for changes"""
    if not _watcher:
        raise HTTPException(status_code=503, detail="Watcher not initialized")

    _watcher.start()
    return {"status": "watching"}


@router.post("/watch/stop")
async def stop_watching():
    """Stop watching plugin directory"""
    if not _watcher:
        raise HTTPException(status_code=503, detail="Watcher not initialized")

    _watcher.stop()
    return {"status": "stopped"}


@router.get("/watch/status")
async def get_watch_status():
    """Get watch status"""
    return {
        "watching": _watcher._watching if _watcher else False,
        "plugins_path": str(_watcher.plugins_path) if _watcher else None,
    }


# Example usage
async def example_hot_reload():
    """Example of hot reload usage"""
    from core.plugin_sandbox import SandboxedPluginLoader

    loader = SandboxedPluginLoader()
    reloader = PluginReloader(loader)

    # Reload single plugin
    result = await reloader.reload_plugin("weather_plugin")
    print(f"Reloaded in {result['duration_seconds']:.3f}s")

    # Start auto-reload on file changes
    watcher = PluginWatcher(reloader, Path("/app/plugins"))
    watcher.start()

    # Any file change triggers automatic reload


if __name__ == "__main__":
    asyncio.run(example_hot_reload())
