"""
Graph Dependencies API Routes

Neo4j graph database integration for managing:
- Plugin dependencies
- Version compatibility
- Conflict detection
- Plugin recommendations
"""

import logging
from enum import Enum
from typing import List, Optional

from core.neo4j_client import Neo4jClient, get_neo4j_client
from fastapi import APIRouter, Depends, HTTPException

from shared.auth.jwt_middleware import get_current_user, get_current_user_or_service
from shared.errors import backend_http_error

logger = logging.getLogger("minder.graph_dependencies")

router = APIRouter(prefix="/v1/graph", tags=["graph-dependencies"])


class DependencyType(str, Enum):
    """Allowed plugin-dependency relationship types.

    Typing the route param with this enum makes FastAPI reject an invalid value with a
    422 (listing the allowed values in /docs) instead of the old free string that only
    failed deep in add_dependency as a caught ValueError → 400 (#143).
    """

    REQUIRES = "requires"
    SUGGESTS = "suggests"
    CONFLICTS_WITH = "conflicts_with"


@router.get("/dependencies/{plugin_id}")
async def get_plugin_dependencies(
    plugin_id: str, neo4j: Neo4jClient = Depends(get_neo4j_client)
):
    """
    Get all dependencies for a plugin (direct and transitive)

    Args:
        plugin_id: Plugin identifier

    Returns:
        List of dependencies with depth information
    """
    try:
        dependencies = await neo4j.get_dependency_chain(plugin_id)
        return {
            "plugin_id": plugin_id,
            "dependencies": dependencies,
            "total_count": len(dependencies),
        }
    except Exception as e:
        logger.error(f"Failed to get dependencies for {plugin_id}: {e}")
        raise backend_http_error(e, "Dependency lookup")


@router.post("/dependencies")
async def add_plugin_dependency(
    plugin_id: str,
    depends_on: str,
    dependency_type: DependencyType = DependencyType.REQUIRES,
    plugin_name: Optional[str] = None,
    depends_on_name: Optional[str] = None,
    neo4j: Neo4jClient = Depends(get_neo4j_client),
    current_user: dict = Depends(get_current_user_or_service),
):
    """
    Add a dependency relationship between two plugins

    Args:
        plugin_id: Plugin that has the dependency
        depends_on: Plugin that is required
        dependency_type: Type of relationship (requires, suggests, conflicts_with)
        plugin_name / depends_on_name: best-effort display names, used ONLY
            if the graph doesn't already have a node for that plugin (see
            Neo4jClient.add_dependency's ON CREATE SET) -- neither node is
            guaranteed to exist yet when this is called (#37).

    Returns:
        Success status

    Accepts the trusted internal service token (in addition to a real user
    JWT) -- plugin-registry's own automated sync populates real edges here
    (e.g. "network requires telegraf") at plugin-load time, with no user
    session in hand (#37).
    """
    try:
        success = await neo4j.add_dependency(
            plugin_id,
            depends_on,
            dependency_type.value,
            plugin_name=plugin_name,
            depends_on_name=depends_on_name,
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to add dependency")

        return {
            "status": "success",
            "plugin_id": plugin_id,
            "depends_on": depends_on,
            "type": dependency_type.value,
        }
    except ValueError as e:
        # Defensive: add_dependency's allowlist is a backstop (the enum already 422s
        # invalid values at the edge).
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add dependency: {e}")
        raise backend_http_error(e, "Dependency creation")


@router.get("/conflicts/{plugin_id}")
async def get_plugin_conflicts(
    plugin_id: str, neo4j: Neo4jClient = Depends(get_neo4j_client)
):
    """
    Find plugins that conflict with the given plugin

    Args:
        plugin_id: Plugin to check

    Returns:
        List of conflicting plugins
    """
    try:
        conflicts = await neo4j.find_conflicting_plugins(plugin_id)
        return {
            "plugin_id": plugin_id,
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
        }
    except Exception as e:
        logger.error(f"Failed to get conflicts for {plugin_id}: {e}")
        raise backend_http_error(e, "Conflict lookup")


@router.post("/recommendations")
async def get_plugin_recommendations(
    installed_plugins: List[str],
    limit: int = 5,
    neo4j: Neo4jClient = Depends(get_neo4j_client),
    current_user: dict = Depends(get_current_user),
):
    """
    Get plugin recommendations based on installed plugins

    Uses collaborative filtering to suggest plugins that are
    commonly used together with installed ones.

    Args:
        installed_plugins: List of installed plugin IDs
        limit: Maximum number of recommendations

    Returns:
        List of recommended plugins with relevance scores
    """
    try:
        recommendations = await neo4j.recommend_plugins(installed_plugins, limit)
        return {
            "installed_plugins": installed_plugins,
            "recommendations": recommendations,
            "count": len(recommendations),
        }
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise backend_http_error(e, "Plugin recommendations")


@router.get("/health")
async def graph_health_check():
    """Check if Neo4j graph database is accessible"""
    try:
        neo4j = await get_neo4j_client()
        # Test connection
        async with neo4j.driver.session() as session:
            result = await session.run("RETURN 1 as test")
            record = await result.single()
            if record and record["test"] == 1:
                return {"status": "healthy", "database": "neo4j"}
            else:
                return {"status": "unhealthy", "database": "neo4j"}
    except Exception as e:
        logger.error(f"Neo4j health check failed: {e}")
        return {"status": "unhealthy", "database": "neo4j", "error": str(e)}
