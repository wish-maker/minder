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

from services.marketplace.config import settings

logger = logging.getLogger("minder.neo4j_client")


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

    async def create_plugin_node(self, plugin_data: Dict[str, Any]) -> str:
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
    ) -> bool:
        """
        Add a dependency relationship between two plugins

        Args:
            plugin_id: Plugin that has the dependency
            depends_on_plugin_id: Plugin that is required
            dependency_type: Type of dependency (requires, suggests, conflicts_with)

        Returns:
            True if successful
        """
        query = f"""
        MATCH (p1:Plugin {{id: $plugin_id}})
        MATCH (p2:Plugin {{id: $depends_on_id}})
        MERGE (p1)-[r:{dependency_type}]->(p2)
        RETURN true
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, plugin_id=plugin_id, depends_on_id=depends_on_plugin_id
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
            return [record.data() for record in await result.list()]

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
            return [record.data() for record in await result.list()]

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
            return [record.data() for record in await result.list()]

    async def get_dependency_chain(self, plugin_id: str) -> List[Dict[str, Any]]:
        """
        Get the full dependency chain for a plugin (transitive dependencies)

        Args:
            plugin_id: Plugin to analyze

        Returns:
            Ordered list of dependencies (direct and transitive)
        """
        query = """
        MATCH path = (p:Plugin {id: $plugin_id})-[:DEPENDS_ON*]->(dependency:Plugin)
        RETURN DISTINCT dependency.id as plugin_id,
               dependency.display_name as name,
               length(path) as depth
        ORDER BY depth DESC
        """

        async with self.driver.session() as session:
            result = await session.run(query, plugin_id=plugin_id)
            return [record.data() for record in await result.list()]


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
