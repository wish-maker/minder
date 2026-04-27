"""
Graph Dependencies API Routes

Neo4j graph database integration for managing:
- Plugin dependencies
- Version compatibility
- Conflict detection
- Plugin recommendations
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
import logging

from services.marketplace.config import settings
from services.marketplace.core.neo4j_client import Neo4jClient, get_neo4j_client

logger = logging.getLogger("minder.graph_dependencies")

router = APIRouter(prefix="/v1/graph", tags=["graph-dependencies"])


@router.get("/dependencies/{plugin_id}")
async def get_plugin_dependencies(
    plugin_id: str,
    neo4j: Neo4jClient = Depends(get_neo4j_client)
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
            "total_count": len(dependencies)
        }
    except Exception as e:
        logger.error(f"Failed to get dependencies for {plugin_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dependencies")
async def add_plugin_dependency(
    plugin_id: str,
    depends_on: str,
    dependency_type: str = "requires",
    neo4j: Neo4jClient = Depends(get_neo4j_client)
):
    """
    Add a dependency relationship between two plugins

    Args:
        plugin_id: Plugin that has the dependency
        depends_on: Plugin that is required
        dependency_type: Type of relationship (requires, suggests, conflicts_with)

    Returns:
        Success status
    """
    try:
        success = await neo4j.add_dependency(plugin_id, depends_on, dependency_type)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to add dependency")

        return {
            "status": "success",
            "plugin_id": plugin_id,
            "depends_on": depends_on,
            "type": dependency_type
        }
    except Exception as e:
        logger.error(f"Failed to add dependency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conflicts/{plugin_id}")
async def get_plugin_conflicts(
    plugin_id: str,
    neo4j: Neo4jClient = Depends(get_neo4j_client)
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
            "conflict_count": len(conflicts)
        }
    except Exception as e:
        logger.error(f"Failed to get conflicts for {plugin_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommendations")
async def get_plugin_recommendations(
    installed_plugins: List[str],
    limit: int = 5,
    neo4j: Neo4jClient = Depends(get_neo4j_client)
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
            "count": len(recommendations)
        }
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
