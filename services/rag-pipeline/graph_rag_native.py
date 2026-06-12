"""
Native Graph RAG Implementation using Neo4j
Eliminates external service dependency by directly querying Neo4j
"""
import logging
import os
from typing import Dict, List, Any, Optional
import httpx

logger = logging.getLogger(__name__)

class NativeGraphRAG:
    """Native Graph RAG using direct Neo4j HTTP API"""

    def __init__(self):
        """Initialize Neo4j connection"""
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "CHANGE_ME_NEO4J_PASSWORD_HERE")
        self.neo4j_http = os.getenv("NEO4J_HTTP", "http://neo4j:7474")

    async def connect(self):
        """Establish Neo4j connection test"""
        try:
            # Test HTTP endpoint
            async with httpx.AsyncClient() as client:
                # Simple connectivity test
                response = await client.get(f"{self.neo4j_http}/db/data/neo4j/tx/commit")
                logger.info("✅ Native Graph RAG: Neo4j HTTP accessible")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Native Graph RAG: Neo4j HTTP test failed: {e}")
            # Return True anyway - will try at query time
            return True

    async def retrieve_graph_context(
        self,
        query: str,
        traversal_depth: int = 2,
        limit: int = 15
    ) -> Dict[str, Any]:
        """Retrieve graph-enhanced context for query using Neo4j HTTP API (RPi 4 optimized)"""
        try:
            # Extract keywords from query (max 3 for RPi 4)
            query_keywords = []
            keywords = ["Neo4j", "graph", "PostgreSQL", "plugin", "RAG", "vector", "database"]
            for keyword in keywords:
                if keyword.lower() in query.lower():
                    query_keywords.append(keyword)
                    if len(query_keywords) >= 3:  # RPi 4 optimization: max 3 keywords
                        break

            if not query_keywords:
                return {"entity_contexts": [], "related_entities": []}

            # Build optimized Cypher query with early LIMIT
            keyword_match = " OR ".join([f"e.name = '{kw}'" for kw in query_keywords[:3]])

            cypher = f"""
            MATCH (e:Entity)
            WHERE {keyword_match}
            WITH e
            MATCH (e)-[r:RELATED_TO*1..{min(traversal_depth, 2)}]-(related:Entity)
            RETURN e.name as entity, e.type as type,
                   collect(r.relationship_type)[0..5] as relationships,
                   related.name as related_entity
            LIMIT {min(limit, 15)}
            """

            # Query Neo4j via HTTP API with timeout (RPi 4 optimization)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.neo4j_http}/db/neo4j/tx/commit",
                    json={
                        "statements": [{
                            "statement": cypher
                        }]
                    },
                    auth=(self.neo4j_user, self.neo4j_password)
                )

                if response.status_code == 200:
                    result = response.json()
                    entity_contexts = []
                    related_entities = []

                    if "results" in result and len(result["results"]) > 0:
                        for record in result["results"][0].get("data", []):
                            if len(record) >= 4:
                                entity_contexts.append({
                                    "entity": record[0],
                                    "type": record[1] if len(record) > 1 else "keyword",
                                    "relationships": record[2] if len(record) > 2 else [],
                                    "related_entity": record[3] if len(record) > 3 else ""
                                })
                                related_entities.append(record[0] if len(record) > 3 else "")

                    logger.info(f"✅ Native Graph RAG: Retrieved {len(entity_contexts)} entity contexts")
                    return {
                        "entity_contexts": entity_contexts,
                        "related_entities": list(set(related_entities))
                    }
                else:
                    logger.warning(f"⚠️ Native Graph RAG: Query failed with status {response.status_code}")
                    return {"entity_contexts": [], "related_entities": []}

        except Exception as e:
            logger.warning(f"⚠️ Native Graph RAG: Graph retrieval failed: {e}")
            return {"entity_contexts": [], "related_entities": []}

    async def close(self):
        """Cleanup - no explicit close needed for HTTP"""
        logger.debug("Native Graph RAG: HTTP connection cleanup")

# Global instance
native_graph_rag = NativeGraphRAG()
