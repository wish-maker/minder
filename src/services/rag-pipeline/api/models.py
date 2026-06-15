"""
API Models

Pydantic models for API request/response validation.
Provides type-safe API contracts for all endpoints.

This is the API layer data models module.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# ============================================================================
# Knowledge Base Models
# ============================================================================

class KnowledgeBaseCreate(BaseModel):
    """Knowledge base creation request"""

    name: str
    description: str
    embedding_model: str = "nomic-embed-text"
    llm_model: str = "llama3"
    chunk_size: int = 512
    chunk_overlap: int = 50
    parent_child_enabled: bool = False


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base response"""

    id: str
    name: str
    description: str
    embedding_model: str
    llm_model: str
    document_count: int
    vector_count: int
    created_at: str


# ============================================================================
# RAG Pipeline Models
# ============================================================================

class RAGPipelineCreate(BaseModel):
    """RAG Pipeline creation request"""

    name: str
    knowledge_base_ids: List[str]
    retrieval_config: Dict[str, Any] = {}
    generation_config: Dict[str, Any] = {}


class QueryRequest(BaseModel):
    """Query request"""

    question: str
    pipeline_id: str
    top_k: int = 5
    stream: bool = False


class QueryResponse(BaseModel):
    """Query response"""

    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    model_used: str
    tokens_used: Optional[int] = None


class DocumentUploadResponse(BaseModel):
    """Document upload response"""

    message: str
    chunks_processed: int
    vectors_created: int
    filename: str


# ============================================================================
# RAPTOR RAG Models
# ============================================================================

class RAPTORUploadRequest(BaseModel):
    """RAPTOR document upload request"""

    file: Any  # UploadFile type from FastAPI
    kb_id: str
    max_tree_depth: int = 3
    cluster_size: int = 6
    summary_length: int = 150


class RAPTORQueryRequest(BaseModel):
    """RAPTOR query request"""

    question: str
    kb_id: str
    top_k: int = 5
    use_raptor: bool = True


class RAPTORTreeInfo(BaseModel):
    """RAPTOR tree structure info"""

    total_nodes: int
    tree_depth: int
    clusters_created: int
    base_chunks: int


class RAPTORUploadResponse(BaseModel):
    """RAPTOR upload response"""

    message: str
    filename: str
    tree_info: RAPTORTreeInfo


# ============================================================================
# Conversation Memory Models
# ============================================================================

class ConversationTurn(BaseModel):
    """Single conversation turn"""

    question: str
    answer: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


class ConversationContextRequest(BaseModel):
    """Request to get conversation context"""

    user_id: str
    conversation_id: str
    current_question: str
    max_turns: int = 3


class ConversationContextResponse(BaseModel):
    """Response with conversation context"""

    user_id: str
    conversation_id: str
    conversation_context: str
    turns_count: int
    turns: List[ConversationTurn]


class StoreConversationRequest(BaseModel):
    """Request to store conversation turn"""

    user_id: str
    conversation_id: str
    question: str
    answer: str
    metadata: Optional[Dict[str, Any]] = None


class StoreConversationResponse(BaseModel):
    """Response after storing conversation"""

    success: bool
    message: str
    user_id: str
    conversation_id: str


class ClearConversationRequest(BaseModel):
    """Request to clear conversation history"""

    user_id: str
    conversation_id: str


class ClearConversationResponse(BaseModel):
    """Response after clearing conversation"""

    success: bool
    message: str


# ============================================================================
# Health Check Models
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str
    version: str
    ollama_available: bool
    qdrant_available: bool
    postgres_available: bool
