"""
Pydantic Models for Graph RAG Service

Request and response schemas for API endpoints.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class EntityExtractionRequest(BaseModel):
    """Request model for entity extraction"""

    # min_length=1: extracting from empty text is a no-op — reject at the edge
    # with a 422 rather than returning a misleading "0 entities" success (#538).
    text: str = Field(..., min_length=1, description="Text to extract entities from")
    extract_relationships: bool = Field(
        default=True, description="Whether to extract relationships between entities"
    )


class KnowledgeGraphRequest(BaseModel):
    """Request model for knowledge graph construction"""

    # min_length=1: document_id is the key the constructed nodes are stored
    # under in Neo4j (an empty id can't be retrieved/managed later), and empty
    # text is nothing to build a graph from — reject both at the edge (#538).
    document_id: str = Field(..., min_length=1, description="Document identifier")
    text: str = Field(..., min_length=1, description="Document text for processing")
    title: str = Field(default="", description="Document title")
    source: str = Field(default="unknown", description="Document source")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional document metadata"
    )
    # Exposed instead of hard-coded True in the handler, matching
    # EntityExtractionRequest (#147).
    extract_relationships: bool = Field(
        default=True, description="Whether to extract relationships between entities"
    )


class GraphRetrievalRequest(BaseModel):
    """Request model for graph-based retrieval"""

    query: str = Field(..., description="Search query for graph retrieval")
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of related entities to retrieve",
    )
    traversal_depth: int = Field(
        default=2, ge=1, le=4, description="Depth of graph traversal"
    )


class EntityContextRequest(BaseModel):
    """Request model for entity context retrieval"""

    entity_text: str = Field(..., description="Entity name to get context for")
    include_neighbors: bool = Field(
        default=True, description="Whether to include connected entities"
    )
    context_window: int = Field(
        default=3, ge=1, le=10, description="Number of related entities to include"
    )


class EntityExtractionResponse(BaseModel):
    """Response model for entity extraction"""

    success: bool
    entities: List[Dict[str, Any]] = Field(
        default_factory=list, description="Extracted entities"
    )
    relationships: List[Dict[str, Any]] = Field(
        default_factory=list, description="Extracted relationships"
    )
    entity_count: int
    relationship_count: int


class KnowledgeGraphResponse(BaseModel):
    """Response model for knowledge graph operations"""

    success: bool
    document_id: str
    entity_count: int = Field(description="Number of entities created")
    relationship_count: int = Field(description="Number of relationships created")
    message: str = Field(default="Graph construction completed")


class GraphRetrievalResponse(BaseModel):
    """Response model for graph retrieval"""

    success: bool
    query: str
    related_entities: List[Dict[str, Any]] = Field(
        default_factory=list, description="Related entities found"
    )
    entity_count: int
    retrieval_time_ms: float = Field(description="Time taken for retrieval")


class EntityContextResponse(BaseModel):
    """Response model for entity context retrieval"""

    success: bool
    entity: Dict[str, Any] = Field(default_factory=dict, description="Entity details")
    related_entities: List[Dict[str, Any]] = Field(
        default_factory=list, description="Related entities"
    )
    documents: List[Dict[str, str]] = Field(
        default_factory=list, description="Documents containing this entity"
    )
    context_window: int
