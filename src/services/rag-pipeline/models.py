"""Pydantic request/response models for the RAG Pipeline API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from config import DEFAULT_EMBEDDING_MODEL, DEFAULT_LLM_MODEL


class KnowledgeBaseCreate(BaseModel):
    """Knowledge base creation request"""

    name: str
    description: str
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    chunk_size: int = 512
    chunk_overlap: int = 50


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


class RAGPipelineCreate(BaseModel):
    """RAG Pipeline creation request"""

    name: str
    knowledge_base_ids: List[str]
    retrieval_config: Dict[str, Any] = {}
    generation_config: Dict[str, Any] = {}


class QueryRequest(BaseModel):
    """Query request"""

    question: str
    top_k: int = 5
    stream: bool = False
    conversation_id: Optional[
        str
    ] = None  # For conversational RAG - enables conversation history
    # standard | hyde | self_rag | auto (decision engine) | corrective (CRAG)
    method: str = "standard"
    # Orthogonal, capability-adaptive post-retrieval enhancers (apply to any method):
    rerank: bool = False  # re-rank sources (cross-encoder if available, else LLM)
    compress: bool = False  # contextual compression of the retrieved context


class QueryResponse(BaseModel):
    """Query response"""

    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    model_used: str
    tokens_used: Optional[int] = None
    method: str = "standard"  # which RAG method actually ran
    method_details: Optional[
        Dict[str, Any]
    ] = None  # e.g. HyDE/Self-RAG/decision metadata


class DocumentUploadResponse(BaseModel):
    """Document upload response"""

    message: str
    chunks_processed: int
    vectors_created: int
    filename: str
