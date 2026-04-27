"""
Minder Plugin Dependency Resolver
Jellyfin-inspired dependency management with topological sorting
"""

import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

import semver

logger = logging.getLogger(__name__)


class DependencyGraph:
    """
    Directed acyclic graph (DAG) for plugin dependencies

    Features:
    - Topological sorting
    - Circular dependency detection
    - Version conflict resolution
    - Dependency distance calculation
    """

    def __init__(self):
        # adjacency list: {plugin: [dependencies]}
        self.graph: Dict[str, List[str]] = defaultdict(list)

        # reverse graph: {plugin: [dependents]}
        self.reverse_graph: Dict[str, List[str]] = defaultdict(list)

        # versions: {plugin: version}
        self.versions: Dict[str, str] = {}

        # metadata: {plugin: {metadata}}
        self.metadata: Dict[str, Dict] = {}

    def add_plugin(self, plugin_id: str, version: str, dependencies: List[str] = None):
        """
        Add plugin to dependency graph

        Args:
            plugin_id: Plugin identifier
            version: Plugin version
            dependencies: List of plugin IDs this plugin depends on
        """
        self.versions[plugin_id] = version
        self.metadata[plugin_id] = {"version": version}

        if dependencies:
            self.graph[plugin_id] = dependencies
            for dep in dependencies:
                self.reverse_graph[dep].append(plugin_id)
        else:
            self.graph[plugin_id] = []

    def remove_plugin(self, plugin_id: str):
        """
        Remove plugin from dependency graph
        """
        # Remove from graph
        if plugin_id in self.graph:
            for dep in self.graph[plugin_id]:
                if dep in self.reverse_graph:
                    self.reverse_graph[dep].remove(plugin_id)
            del self.graph[plugin_id]

        # Remove from reverse graph
        if plugin_id in self.reverse_graph:
            del self.reverse_graph[plugin_id]

        # Remove versions and metadata
        self.versions.pop(plugin_id, None)
        self.metadata.pop(plugin_id, None)

    def get_dependencies(self, plugin_id: str) -> List[str]:
        """Get direct dependencies of a plugin"""
        return self.graph.get(plugin_id, [])

    def get_dependents(self, plugin_id: str) -> List[str]:
        """Get plugins that depend on this plugin"""
        return self.reverse_graph.get(plugin_id, [])

    def has_circular_dependencies(self) -> bool:
        """
        Check if graph has circular dependencies

        Returns:
            True if circular dependencies detected
        """
        visited = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)

            for neighbor in self.graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for plugin in self.graph:
            if plugin not in visited:
                if dfs(plugin):
                    return True

        return False

    def find_circular_dependencies(self) -> List[List[str]]:
        """
        Find all circular dependencies in the graph

        Returns:
            List of circular dependency chains
        """
        cycles = []

        def find_cycle(node, path, visited):
            if node in path:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            for neighbor in self.graph.get(node, []):
                find_cycle(neighbor, path.copy(), visited)

        visited = set()
        for plugin in self.graph:
            if plugin not in visited:
                find_cycle(plugin, [], visited)

        return cycles

    def topological_sort(self) -> List[str]:
        """
        Perform topological sort on dependency graph

        Returns:
            List of plugin IDs in dependency order (dependencies first)

        Raises:
            ValueError if graph has circular dependencies
        """
        if self.has_circular_dependencies():
            cycles = self.find_circular_dependencies()
            raise ValueError(f"Cannot sort: Circular dependencies detected: {cycles}")

        in_degree = {node: 0 for node in self.graph}

        # Calculate in-degrees
        for node in self.graph:
            for neighbor in self.graph[node]:
                in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

        # Queue for nodes with no dependencies
        queue = deque([node for node in in_degree if in_degree[node] == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)

            # Reduce in-degree for neighbors
            for neighbor in self.graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.graph):
            raise ValueError("Graph has a cycle (topological sort incomplete)")

        return result

    def get_load_order(self, plugin_id: str) -> List[str]:
        """
        Get load order for a specific plugin (dependencies first)

        Args:
            plugin_id: Plugin to load

        Returns:
            List of plugin IDs in load order
        """
        # Get all dependencies recursively
        visited = set()
        load_order = []

        def dfs(node):
            if node in visited:
                return

            visited.add(node)

            # Visit dependencies first
            for dep in self.graph.get(node, []):
                dfs(dep)

            load_order.append(node)

        dfs(plugin_id)
        return load_order

    def get_unload_order(self, plugin_id: str) -> List[str]:
        """
        Get unload order for a specific plugin (dependents first)

        Args:
            plugin_id: Plugin to unload

        Returns:
            List of plugin IDs in unload order
        """
        # Get all dependents recursively
        visited = set()
        unload_order = []

        def dfs(node):
            if node in visited:
                return

            visited.add(node)

            # Visit dependents first
            for dependent in self.reverse_graph.get(node, []):
                dfs(dependent)

            unload_order.append(node)

        dfs(plugin_id)
        return unload_order


class DependencyResolver:
    """
    Jellyfin-style dependency resolver for Minder plugins

    Features:
    - Dependency graph construction
    - Topological sorting
    - Circular dependency detection
    - Version conflict detection
    - Missing dependency detection
    """

    def __init__(self):
        self.graph = DependencyGraph()
        self.installed_plugins: Dict[str, Dict] = {}

    def add_plugin(self, plugin_id: str, manifest: Dict):
        """
        Add plugin to dependency resolver

        Args:
            plugin_id: Plugin identifier
            manifest: Plugin manifest dict
        """
        version = manifest.get("version", "0.0.0")
        dependencies = manifest.get("dependencies", {}).get("plugins", [])

        # Extract dependency IDs and versions
        dep_list = []
        for dep in dependencies:
            dep_id = dep.get("id")
            if dep_id:
                dep_list.append(dep_id)

        self.graph.add_plugin(plugin_id, version, dep_list)
        self.installed_plugins[plugin_id] = manifest

        logger.info(f"✅ Added plugin to dependency graph: {plugin_id}")

    def resolve_load_order(self, plugin_ids: List[str]) -> List[str]:
        """
        Resolve load order for multiple plugins

        Args:
            plugin_ids: List of plugin IDs to load

        Returns:
            List of plugin IDs in correct load order

        Raises:
            ValueError if circular dependencies detected
        """
        # Build subgraph with only requested plugins
        subgraph = DependencyGraph()

        for plugin_id in plugin_ids:
            if plugin_id in self.installed_plugins:
                manifest = self.installed_plugins[plugin_id]
                version = manifest.get("version", "0.0.0")
                dependencies = manifest.get("dependencies", {}).get("plugins", [])

                dep_list = [dep.get("id") for dep in dependencies if dep.get("id")]
                subgraph.add_plugin(plugin_id, version, dep_list)

        # Return topological sort
        return subgraph.topological_sort()

    def check_dependencies(self, plugin_id: str) -> Dict[str, List[str]]:
        """
        Check plugin dependencies

        Args:
            plugin_id: Plugin to check

        Returns:
            Dict with:
            - "missing": List of missing dependencies
            - "satisfied": List of satisfied dependencies
            - "conflicts": List of version conflicts
        """
        result = {"missing": [], "satisfied": [], "conflicts": []}

        if plugin_id not in self.installed_plugins:
            result["missing"].append(f"Plugin {plugin_id} not found in registry")
            return result

        manifest = self.installed_plugins[plugin_id]
        dependencies = manifest.get("dependencies", {}).get("plugins", [])

        for dep in dependencies:
            dep_id = dep.get("id")
            dep_version_req = dep.get("version", "*")

            if not dep_id:
                continue

            if dep_id not in self.installed_plugins:
                result["missing"].append(dep_id)
            else:
                # Check version compatibility
                installed_version = self.installed_plugins[dep_id].get("version", "0.0.0")

                if not self._check_version_compat(installed_version, dep_version_req):
                    result["conflicts"].append(
                        f"{dep_id}: requires {dep_version_req}, has {installed_version}"
                    )
                else:
                    result["satisfied"].append(dep_id)

        return result

    def detect_conflicts(self, plugin_id: str, new_version: str) -> List[str]:
        """
        Detect version conflicts with existing plugins

        Args:
            plugin_id: Plugin to check
            new_version: New version to install

        Returns:
            List of conflicting plugins
        """
        conflicts = []

        # Check if plugin is already installed with different version
        if plugin_id in self.installed_plugins:
            current_version = self.installed_plugins[plugin_id].get("version", "0.0.0")

            if current_version != new_version:
                # Check if this would break dependents
                dependents = self.graph.get_dependents(plugin_id)

                for dependent in dependents:
                    dep_manifest = self.installed_plugins.get(dependent, {})
                    dep_dependencies = dep_manifest.get("dependencies", {}).get("plugins", [])

                    for dep in dep_dependencies:
                        if dep.get("id") == plugin_id:
                            required_version = dep.get("version", "*")

                            if not self._check_version_compat(new_version, required_version):
                                conflicts.append(
                                    f"{dependent} requires {plugin_id} {required_version}, "
                                    f"but new version is {new_version}"
                                )

        return conflicts

    def get_installation_order(self, plugin_id: str) -> List[str]:
        """
        Get installation order for a plugin (dependencies first)

        Args:
            plugin_id: Plugin to install

        Returns:
            List of plugin IDs in installation order
        """
        return self.graph.get_load_order(plugin_id)

    def get_removal_order(self, plugin_id: str) -> List[str]:
        """
        Get removal order for a plugin (dependents first)

        Args:
            plugin_id: Plugin to remove

        Returns:
            List of plugin IDs in removal order
        """
        return self.graph.get_unload_order(plugin_id)

    def get_dependency_tree(self, plugin_id: str) -> Dict:
        """
        Get complete dependency tree for a plugin

        Args:
            plugin_id: Root plugin

        Returns:
            Nested dict representing dependency tree
        """

        def build_tree(node, visited):
            if node in visited:
                return {"id": node, "circular": True}

            visited.add(node)

            dependencies = self.graph.get_dependencies(node)
            children = [build_tree(dep, visited.copy()) for dep in dependencies]

            return {
                "id": node,
                "version": self.graph.versions.get(node, "unknown"),
                "dependencies": children,
            }

        return build_tree(plugin_id, set())

    def _check_version_compat(self, installed_version: str, required_range: str) -> bool:
        """
        Check if installed version satisfies required range

        Args:
            installed_version: Currently installed version
            required_range: Required version range (e.g., ">=1.0.0", "2.x")

        Returns:
            True if compatible
        """
        try:
            # Parse versions
            installed = semver.VersionInfo.parse(installed_version)

            # Handle wildcard versions
            if required_range == "*":
                return True

            # Parse requirement
            if required_range.startswith(">="):
                min_version = semver.VersionInfo.parse(required_range[2:])
                return installed >= min_version
            elif required_range.startswith("<="):
                max_version = semver.VersionInfo.parse(required_range[2:])
                return installed <= max_version
            elif required_range.startswith(">"):
                min_version = semver.VersionInfo.parse(required_range[1:])
                return installed > min_version
            elif required_range.startswith("<"):
                max_version = semver.VersionInfo.parse(required_range[1:])
                return installed < max_version
            elif required_range.startswith("="):
                exact_version = semver.VersionInfo.parse(required_range[1:])
                return installed == exact_version
            else:
                # Exact version match
                exact_version = semver.VersionInfo.parse(required_range)
                return installed == exact_version

        except (ValueError, semver.VersionParseError):
            # If version parsing fails, assume compatible
            logger.warning(f"Failed to parse versions: {installed_version} vs {required_range}")
            return True

    def get_statistics(self) -> Dict:
        """
        Get dependency graph statistics

        Returns:
            Dict with graph statistics
        """
        return {
            "total_plugins": len(self.graph.versions),
            "has_circular_deps": self.graph.has_circular_dependencies(),
            "circular_deps": self.graph.find_circular_dependencies(),
            "most_dependent": max(
                [(pid, len(self.graph.get_dependents(pid))) for pid in self.graph.versions],
                key=lambda x: x[1],
                default=(None, 0),
            ),
            "most_dependencies": max(
                [(pid, len(self.graph.get_dependencies(pid))) for pid in self.graph.versions],
                key=lambda x: x[1],
                default=(None, 0),
            ),
        }
