"""
Pydantic Models for Graph RAG Service

Request and response schemas for API endpoints.
"""

from typing import Any, Dict, List, Optional

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
    # #782: optional knowledge-base grouping key stored on the Document. The
    # tenant/isolation boundary itself is the authenticated caller (owner_id,
    # taken from the JWT `sub` in the route — NEVER from the request body, or a
    # client could claim another tenant's scope); kb_id is a finer, owner-local
    # grouping label a caller may filter their own documents by.
    kb_id: Optional[str] = Field(
        default=None, description="Optional knowledge-base grouping key (owner-local)"
    )
    # Optional/None (not ""/"unknown"/{}) so an OMITTED field on a re-POST is
    # distinguishable from an explicit value: construct_graph COALESCEs None to the
    # previously-stored value instead of blanking it (#668 item 3).
    title: Optional[str] = Field(default=None, description="Document title")
    source: Optional[str] = Field(default=None, description="Document source")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional document metadata"
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


class GraphSearchRequest(BaseModel):
    """Request model for free-text entity search over the knowledge graph."""

    query: str = Field(
        ..., min_length=1, description="Text matched against entity text and label"
    )
    limit: int = Field(
        default=5, ge=1, le=50, description="Maximum number of entities to return"
    )


class GraphSearchResponse(BaseModel):
    """Response model for graph entity search."""

    success: bool
    query: str
    entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Matching entities (text/label/description)",
    )
    entity_count: int


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


class GraphDocument(BaseModel):
    """One Document node in the knowledge graph."""

    id: str
    title: Optional[str] = None
    source: Optional[str] = None
    kb_id: Optional[str] = Field(
        default=None, description="Owner-local knowledge-base grouping key (#782)"
    )
    created_at: Optional[str] = None
    entity_count: int = Field(default=0, description="Entities this document mentions")


class GraphDocumentsResponse(BaseModel):
    """Response model for listing the graph's Document nodes."""

    success: bool
    documents: List[GraphDocument] = Field(default_factory=list)
    count: int = Field(description="Number of documents in the graph")


class GraphStatsResponse(BaseModel):
    """Response model for a knowledge-graph overview."""

    success: bool
    nodes: int = Field(description="Total node count (all labels)")
    relationships: int = Field(description="Total relationship count")
    documents: int = Field(description="Number of Document nodes")
    entities: int = Field(description="Number of Entity nodes")
    entity_types: Dict[str, int] = Field(
        default_factory=dict,
        description="Entity count per NER label (e.g. PERSON, ORG), most first",
    )
