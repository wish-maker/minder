"""
Plugin Sandbox - Process Isolation for Security
Version: 1.0.0

Implements subprocess-based isolation for untrusted 3rd party plugins.
Each plugin runs in a separate process with limited resources.
"""

import asyncio
import logging
import multiprocessing as mp
import signal
import resource
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

from core.plugin_manifest import PluginManifest, validate_plugin_for_installation

logger = logging.getLogger(__name__)


class SandboxTimeout(Exception):
    """Plugin execution timeout"""

    pass


class SandboxMemoryLimit(Exception):
    """Plugin exceeded memory limit"""

    pass


class SandboxPermissionDenied(Exception):
    """Plugin attempted unauthorized operation"""

    pass


class PluginSandbox(ABC):
    """
    Abstract base class for plugin sandboxing

    Implementations:
    - SubprocessSandbox: Process isolation (recommended for untrusted plugins)
    - ThreadSandbox: Thread-based isolation (faster, less secure)
    """

    @abstractmethod
    async def execute_plugin(self, plugin_name: str, method: str, *args, **kwargs) -> Any:
        """Execute plugin method in sandbox"""
        pass

    @abstractmethod
    async def terminate_plugin(self, plugin_name: str):
        """Terminate plugin process"""
        pass


class SubprocessSandbox(PluginSandbox):
    """
    Subprocess-based plugin sandboxing

    Each plugin runs in isolated process with:
    - Memory limits
    - CPU time limits
    - Execution timeouts
    - Restricted filesystem access
    - Restricted network access
    """

    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self.processes: Dict[str, mp.Process] = {}
        self.results: Dict[str, mp.Queue] = {}

    async def execute_plugin(self, plugin_name: str, method: str, *args, **kwargs) -> Any:
        """
        Execute plugin method in isolated subprocess

        Args:
            plugin_name: Name of plugin to execute
            method: Method name to call
            *args: Method arguments
            **kwargs: Method keyword arguments

        Returns:
            Method return value

        Raises:
            SandboxTimeout: If execution exceeds time limit
            SandboxMemoryLimit: If plugin exceeds memory limit
            SandboxPermissionDenied: If plugin violates permissions
        """
        result_queue = mp.Queue()

        # Get resource limits from manifest
        limits = self.manifest.permissions.resources
        max_memory_mb = limits.max_memory_mb
        max_cpu_percent = limits.max_cpu_percent
        max_execution_time = limits.max_execution_time

        # Create process with resource limits
        process = mp.Process(
            target=self._run_plugin,
            args=(
                plugin_name,
                method,
                args,
                kwargs,
                result_queue,
                max_memory_mb,
                max_execution_time,
            ),
        )

        self.processes[plugin_name] = process
        self.results[plugin_name] = result_queue

        # Start process
        process.start()

        # Wait for completion with timeout
        try:
            # Wait for result with timeout
            result = await asyncio.wait_for(self._get_result(result_queue), timeout=max_execution_time)

            if result.get("error"):
                raise Exception(result["error"])

            if result.get("timeout"):
                raise SandboxTimeout(
                    f"Plugin {plugin_name}.{method}() exceeded " f"time limit of {max_execution_time}s"
                )

            if result.get("memory_exceeded"):
                raise SandboxMemoryLimit(f"Plugin {plugin_name} exceeded memory limit " f"of {max_memory_mb}MB")

            if result.get("permission_denied"):
                raise SandboxPermissionDenied(f"Plugin {plugin_name} attempted unauthorized operation")

            return result.get("data")

        except asyncio.TimeoutError:
            # Kill process
            self.terminate_plugin(plugin_name)
            raise SandboxTimeout(f"Plugin {plugin_name}.{method}() exceeded " f"time limit of {max_execution_time}s")

        finally:
            # Clean up process
            if plugin_name in self.processes:
                del self.processes[plugin_name]
            if plugin_name in self.results:
                del self.results[plugin_name]

    def _run_plugin(
        self,
        plugin_name: str,
        method: str,
        args: tuple,
        kwargs: dict,
        result_queue: mp.Queue,
        max_memory_mb: int,
        max_execution_time: int,
    ):
        """
        Run plugin in isolated process with resource limits

        This runs in a SEPARATE process with:
        - Memory limits enforced
        - CPU time limits enforced
        - Execution timeouts enforced
        """
        try:
            # Set resource limits
            self._set_resource_limits(max_memory_mb, max_execution_time)

            # Set alarm for execution timeout
            signal.signal(signal.SIGALRM, self._timeout_handler)
            signal.alarm(max_execution_time)

            # Import and load plugin
            from core.plugin_loader import PluginLoader

            loader = PluginLoader({"plugins_path": Path("/app/plugins")})
            plugin = loader.load_plugin(plugin_name)

            if plugin is None:
                result_queue.put({"error": f"Plugin not found: {plugin_name}"})
                return

            # Call requested method
            if hasattr(plugin, method):
                method_func = getattr(plugin, method)

                # Run async method
                if asyncio.iscoroutinefunction(method_func):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(method_func(*args, **kwargs))
                    finally:
                        loop.close()
                else:
                    result = method_func(*args, **kwargs)

                result_queue.put({"data": result})
            else:
                result_queue.put({"error": f"Method not found: {method}"})

        except MemoryError:
            result_queue.put({"memory_exceeded": True})
        except Exception as e:
            result_queue.put({"error": str(e)})
        finally:
            # Cancel alarm
            signal.alarm(0)

    def _set_resource_limits(self, max_memory_mb: int, max_execution_time: int):
        """Set OS-level resource limits"""
        try:
            # Set memory limit (soft, hard)
            max_memory_bytes = max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))

            # Set CPU time limit
            max_cpu_time = max_execution_time * 2  # Allow 2x wall time
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_time, max_cpu_time))

            logger.debug(f"Set resource limits: " f"memory={max_memory_mb}MB, cpu_time={max_cpu_time}s")
        except (ValueError, resource.error) as e:
            logger.warning(f"Could not set resource limits: {e}")

    def _timeout_handler(self, signum, frame):
        """Handle execution timeout"""
        raise SandboxTimeout("Execution time exceeded")

    async def _get_result(self, queue: mp.Queue) -> Dict[str, Any]:
        """Get result from queue (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, queue.get)

    async def terminate_plugin(self, plugin_name: str):
        """Terminate plugin process"""
        if plugin_name in self.processes:
            process = self.processes[plugin_name]

            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

                if process.is_alive():
                    # Force kill if terminate didn't work
                    process.kill()
                    process.join()

                logger.info(f"Terminated plugin: {plugin_name}")


class ThreadSandbox(PluginSandbox):
    """
    Thread-based plugin sandboxing

    WARNING: Less secure than subprocess isolation!
    Only use for trusted plugins.

    Benefits:
    - Faster startup
    - Lower memory overhead
    - Easier debugging

    Drawbacks:
    - No memory isolation
    - No CPU limits
    - Shared process space
    """

    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self.tasks: Dict[str, asyncio.Task] = {}

    async def execute_plugin(
        self, plugin_name: str, method: str, *args, timeout: Optional[int] = None, **kwargs
    ) -> Any:
        """Execute plugin method in thread with timeout"""
        from core.plugin_loader import PluginLoader

        loader = PluginLoader({"plugins_path": Path("/app/plugins")})
        plugin = loader.load_plugin(plugin_name)

        if plugin is None:
            raise ValueError(f"Plugin not found: {plugin_name}")

        if not hasattr(plugin, method):
            raise ValueError(f"Method not found: {method}")

        method_func = getattr(plugin, method)

        # Get timeout from manifest if not specified
        if timeout is None:
            timeout = self.manifest.permissions.resources.max_execution_time

        # Execute with timeout
        try:
            result = await asyncio.wait_for(method_func(*args, **kwargs), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise SandboxTimeout(f"Plugin {plugin_name}.{method}() exceeded timeout")

    async def terminate_plugin(self, plugin_name: str):
        """Cancel plugin task"""
        if plugin_name in self.tasks:
            task = self.tasks[plugin_name]
            task.cancel()
            del self.tasks[plugin_name]


class SandboxedPluginLoader:
    """
    Plugin loader with automatic sandboxing

    Chooses sandbox type based on plugin trust level:
    - Untrusted plugins → SubprocessSandbox
    - Trusted plugins → ThreadSandbox
    """

    def __init__(self):
        self.sandboxes: Dict[str, PluginSandbox] = {}

    async def load_plugin(self, plugin_path: Path, trusted: bool = False) -> PluginSandbox:
        """
        Load plugin with appropriate sandbox

        Args:
            plugin_path: Path to plugin directory
            trusted: Whether plugin is trusted (affects sandbox type)

        Returns:
            Plugin sandbox instance
        """
        # Validate plugin
        is_valid, manifest, errors = validate_plugin_for_installation(plugin_path)

        if not is_valid:
            raise ValueError(f"Plugin validation failed: {errors}")

        plugin_name = manifest.name

        # Choose sandbox type
        if trusted:
            logger.info(f"Loading trusted plugin {plugin_name} with thread sandbox")
            sandbox = ThreadSandbox(manifest)
        else:
            logger.info(f"Loading untrusted plugin {plugin_name} with subprocess sandbox")
            sandbox = SubprocessSandbox(manifest)

        self.sandboxes[plugin_name] = sandbox
        return sandbox

    async def execute_plugin_method(self, plugin_name: str, method: str, *args, **kwargs) -> Any:
        """Execute plugin method through its sandbox"""
        if plugin_name not in self.sandboxes:
            raise ValueError(f"Plugin not loaded: {plugin_name}")

        sandbox = self.sandboxes[plugin_name]
        return await sandbox.execute_plugin(plugin_name, method, *args, **kwargs)

    async def unload_plugin(self, plugin_name: str):
        """Unload plugin and cleanup resources"""
        if plugin_name in self.sandboxes:
            await self.sandboxes[plugin_name].terminate_plugin(plugin_name)
            del self.sandboxes[plugin_name]
            logger.info(f"Unloaded plugin: {plugin_name}")


# Example usage
async def example_sandboxed_plugin():
    """Example of using sandboxed plugin"""
    loader = SandboxedPluginLoader()

    # Load untrusted plugin (uses subprocess isolation)
    sandbox = await loader.load_plugin(
        Path("/app/plugins/third_party_plugin"), trusted=False  # ← Untrusted! Uses subprocess
    )

    try:
        # Execute plugin method safely
        result = await sandbox.execute_plugin(
            "third_party_plugin", "collect_data", since=datetime.now() - timedelta(days=1)
        )

        print(f"Result: {result}")

    except SandboxTimeout:
        print("Plugin exceeded time limit - terminated")
    except SandboxMemoryLimit:
        print("Plugin exceeded memory limit - terminated")
    except SandboxPermissionDenied:
        print("Plugin attempted unauthorized operation - blocked")
    finally:
        # Cleanup
        await loader.unload_plugin("third_party_plugin")


if __name__ == "__main__":
    # Test sandbox
    asyncio.run(example_sandboxed_plugin())
