"""
Neo4j Graph Database Client for Minder Plugin Marketplace

This module handles all graph database operations including:
- Plugin dependencies
- Version compatibility
- Conflict detection
- Recommendations
"""

import logging
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase

from config import settings

logger = logging.getLogger("minder.neo4j_client")

# Cap on transitive DEPENDS_ON traversal depth (#673). With the write-time cycle
# guard in add_dependency the graph stays acyclic, so this is defense-in-depth: it
# bounds the search space against a pre-existing cycle in a live graph (from before
# the guard) and keeps the unbounded `*` pattern from exploding on a large/densely-
# connected graph. Generous enough for any realistic plugin dependency chain.
MAX_DEPENDENCY_DEPTH = 20


def _parse_neo4j_auth(auth_string: str) -> tuple[str, str]:
    """
    Parse NEO4J_AUTH string (format: neo4j/password) into user and password.

    Args:
        auth_string: Auth string in format "user/password"

    Returns:
        Tuple of (username, password)
    """
    if "/" in auth_string:
        user, password = auth_string.split("/", 1)
        return user, password
    # Fallback to default if format is wrong
    return "neo4j", auth_string


class Neo4jClient:
    """Neo4j graph database client for managing plugin relationships"""

    def __init__(
        self,
        uri: str = "bolt://neo4j:7687",
        user: str = "neo4j",
        password: str = "",
    ):
        """
        Initialize Neo4j client

        Args:
            uri: Neo4j Bolt protocol URI
            user: Neo4j username
            password: Neo4j password
        """
        # If password not provided, use from settings (platform standard)
        if not password and hasattr(settings, "NEO4J_AUTH"):
            user, password = _parse_neo4j_auth(settings.NEO4J_AUTH)
        elif not password:
            # Last resort: should not happen in production
            password = "secure_password_change_me"

        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self):
        """Close the database connection"""
        await self.driver.close()

    async def create_plugin_node(self, plugin_data: Dict[str, Any]) -> Optional[str]:
        """
        Create or update a plugin node in the graph

        Args:
            plugin_data: Plugin metadata from marketplace

        Returns:
            Plugin ID
        """
        query = """
        MERGE (p:Plugin {id: $id})
        SET p += $properties
        RETURN p.id as plugin_id
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, id=plugin_data["id"], properties=plugin_data
            )
            record = await result.single()
            return record["plugin_id"] if record else None

    async def add_dependency(
        self,
        plugin_id: str,
        depends_on_plugin_id: str,
        dependency_type: str = "requires",
        plugin_name: Optional[str] = None,
        depends_on_name: Optional[str] = None,
    ) -> bool:
        """
        Add a dependency relationship between two plugins

        Args:
            plugin_id: Plugin that has the dependency
            depends_on_plugin_id: Plugin that is required
            dependency_type: Type of dependency (requires, suggests, conflicts_with)
            plugin_name: best-effort display name for `plugin_id`, set on the
                node ONLY if it doesn't already have one (see coalesce below)
            depends_on_name: same, for `depends_on_plugin_id`

        Returns:
            True if successful

        Found live: this used MATCH for both plugin nodes, which requires
        them to already exist -- but nothing anywhere ever calls
        create_plugin_node, so BOTH nodes were always missing and this
        silently returned False for every real call (the route above turns
        that into a 400, so at least visibly -- but the underlying edge
        never gets created). MERGE makes this self-sufficient: a dependency
        can be recorded for a plugin before or after its own full node ever
        gets created some other way, same self-healing spirit as
        marketplace_sync.py's own "bare placeholder, reconciled later" path
        for a plugin that hasn't synced yet.
        """
        # Cypher cannot parameterize a relationship type, so the type is
        # interpolated into the query string. Guard against Cypher injection with a
        # strict allowlist of literal, safe relationship types — the caller-supplied
        # dependency_type is NEVER interpolated directly. The original value is also
        # stored as a property so reads (r.dependency_type) still see it.
        #
        # Found live: this used to map "requires"/"suggests" to their own
        # literal relationship names (REQUIRES/SUGGESTS), but every reader
        # (get_plugin_dependencies, get_dependency_chain, recommend_plugins)
        # queries :DEPENDS_ON / :RECOMMENDS specifically -- a real plugin
        # dependency (e.g. "network requires telegraf") could be written
        # here and would NEVER show up anywhere, silently. dependency_type
        # is already stored as a property on the edge (see SET below), so
        # the relationship label itself only needs to match what's read;
        # "conflicts_with" -> CONFLICTS_WITH already matched find_conflicting_
        # plugins and is unchanged.
        allowed_rel_types = {
            "requires": "DEPENDS_ON",
            "suggests": "RECOMMENDS",
            "conflicts_with": "CONFLICTS_WITH",
        }
        rel_type = allowed_rel_types.get(dependency_type)
        if rel_type is None:
            raise ValueError(
                f"Invalid dependency_type {dependency_type!r}; "
                f"allowed: {sorted(allowed_rel_types)}"
            )

        # A plugin depending on / recommending / conflicting-with itself is always a
        # mistake (#673). Without this, a self-loop `A DEPENDS_ON A` makes
        # get_dependency_chain("A") return A as one of its own transitive
        # dependencies. Reject before any write; the route maps ValueError -> 400.
        if plugin_id == depends_on_plugin_id:
            raise ValueError(
                f"A plugin cannot {dependency_type} itself (plugin_id "
                f"{plugin_id!r} == depends_on_plugin_id)"
            )

        query = f"""
        MERGE (p1:Plugin {{id: $plugin_id}})
        ON CREATE SET p1.display_name = $plugin_name
        MERGE (p2:Plugin {{id: $depends_on_id}})
        ON CREATE SET p2.display_name = $depends_on_name
        MERGE (p1)-[r:{rel_type}]->(p2)
        SET r.dependency_type = $dependency_type
        RETURN true
        """  # nosec B608 - rel_type is from a fixed allowlist, not user input

        async with self.driver.session() as session:
            # Cycle guard (#673): adding `p1 -[:DEPENDS_ON]-> p2` closes a cycle iff
            # p2 already (transitively) depends on p1. Neo4j's `*` traversal can
            # revisit nodes, so an unguarded cycle makes get_dependency_chain report
            # a plugin as its own dependency. Probe first and reject rather than
            # create the edge. Only DEPENDS_ON forms a meaningful dependency cycle;
            # RECOMMENDS/CONFLICTS_WITH self-loops are already caught above.
            if rel_type == "DEPENDS_ON":
                cycle_probe = f"""
                MATCH path = (start:Plugin {{id: $depends_on_id}})
                      -[:DEPENDS_ON*1..{MAX_DEPENDENCY_DEPTH}]->
                      (target:Plugin {{id: $plugin_id}})
                RETURN path LIMIT 1
                """  # nosec B608 - only the fixed int MAX_DEPENDENCY_DEPTH is interpolated
                probe_result = await session.run(
                    cycle_probe,
                    plugin_id=plugin_id,
                    depends_on_id=depends_on_plugin_id,
                )
                if await probe_result.single() is not None:
                    raise ValueError(
                        f"Adding dependency {plugin_id!r} -> "
                        f"{depends_on_plugin_id!r} would create a cycle in the "
                        "DEPENDS_ON graph"
                    )

            result = await session.run(
                query,
                plugin_id=plugin_id,
                depends_on_id=depends_on_plugin_id,
                dependency_type=dependency_type,
                plugin_name=plugin_name or plugin_id,
                depends_on_name=depends_on_name or depends_on_plugin_id,
            )
            record = await result.single()
            return record["true"] if record else False

    async def get_plugin_dependencies(self, plugin_id: str) -> List[Dict[str, Any]]:
        """
        Get all dependencies for a plugin

        Args:
            plugin_id: Plugin to query

        Returns:
            List of dependencies
        """
        query = """
        MATCH (p:Plugin {id: $plugin_id})-[r:DEPENDS_ON]->(other:Plugin)
        RETURN other.id as plugin_id, other.display_name as name, r.dependency_type as type
        """

        async with self.driver.session() as session:
            result = await session.run(query, plugin_id=plugin_id)
            return await result.data()

    async def find_conflicting_plugins(self, plugin_id: str) -> List[Dict[str, Any]]:
        """
        Find plugins that conflict with the given plugin

        Args:
            plugin_id: Plugin to check

        Returns:
            List of conflicting plugins
        """
        query = """
        MATCH (p:Plugin {id: $plugin_id})-[r:CONFLICTS_WITH]-(other:Plugin)
        RETURN other.id as plugin_id, other.display_name as name, r.reason as reason
        """

        async with self.driver.session() as session:
            result = await session.run(query, plugin_id=plugin_id)
            return await result.data()

    async def recommend_plugins(
        self, installed_plugin_ids: List[str], limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Recommend plugins based on installed ones using collaborative filtering

        Args:
            installed_plugin_ids: List of installed plugin IDs
            limit: Maximum number of recommendations

        Returns:
            List of recommended plugins with scores
        """
        query = """
        MATCH (installed:Plugin)
        WHERE installed.id IN $installed_ids
        MATCH (installed)-[:DEPENDS_ON|RECOMMENDS]->(recommended:Plugin)
        WHERE NOT recommended.id IN $installed_ids
        RETURN recommended.id as plugin_id,
               recommended.display_name as name,
               count(*) as score
        ORDER BY score DESC
        LIMIT $limit
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, installed_ids=installed_plugin_ids, limit=limit
            )
            return await result.data()

    async def get_dependency_chain(self, plugin_id: str) -> List[Dict[str, Any]]:
        """
        Get the full dependency chain for a plugin (transitive dependencies)

        Args:
            plugin_id: Plugin to analyze

        Returns:
            Ordered list of dependencies (direct and transitive)
        """
        # Depth-capped `*1..N` rather than unbounded `*` (#673): defense-in-depth so a
        # pre-existing cycle (from before add_dependency's write-time guard) can't make
        # this traversal explode combinatorially on a densely-connected graph.
        query = f"""
        MATCH path = (p:Plugin {{id: $plugin_id}})
              -[:DEPENDS_ON*1..{MAX_DEPENDENCY_DEPTH}]->(dependency:Plugin)
        RETURN DISTINCT dependency.id as plugin_id,
               dependency.display_name as name,
               length(path) as depth
        ORDER BY depth DESC
        """  # nosec B608 - only the fixed int MAX_DEPENDENCY_DEPTH is interpolated

        async with self.driver.session() as session:
            result = await session.run(query, plugin_id=plugin_id)
            return await result.data()


# Singleton instance
_neo4j_client: Optional[Neo4jClient] = None


async def get_neo4j_client() -> Neo4jClient:
    """
    Get or create the Neo4j client singleton

    Returns:
        Neo4j client instance
    """
    global _neo4j_client

    if _neo4j_client is None:
        # Use settings.NEO4J_URI if available, otherwise default
        uri = getattr(settings, "NEO4J_URI", "bolt://neo4j:7687")

        # Parse user/password from NEO4J_AUTH
        if hasattr(settings, "NEO4J_AUTH") and settings.NEO4J_AUTH:
            user, password = _parse_neo4j_auth(settings.NEO4J_AUTH)
        else:
            # Fallback - should not happen in production
            user = "neo4j"
            password = "secure_password_change_me"

        _neo4j_client = Neo4jClient(uri=uri, user=user, password=password)

    return _neo4j_client
