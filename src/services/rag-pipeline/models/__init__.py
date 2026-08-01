"""Pydantic request/response models for the RAG Pipeline API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from config import DEFAULT_EMBEDDING_MODEL, DEFAULT_LLM_MODEL

# Canonical set of selectable generation/retrieval-rewrite strategies (the `method`
# field). "conversational" is NOT here — it is activated by passing `conversation_id`,
# not by `method`. Retrieval strategies (hybrid/parent_context) are separate boolean
# flags, not methods. Kept here (not in rag/runner) so the request model can reject an
# unknown method with a 422 at the API edge instead of silently coercing to standard.
VALID_RAG_METHODS = {"standard", "hyde", "self_rag", "auto", "corrective"}


class KnowledgeBaseCreate(BaseModel):
    """Knowledge base creation request"""

    name: str
    # Optional — a description shouldn't be required to create a KB (#144).
    description: str = ""
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
    # At least one KB: retrieval reads knowledge_base_ids[0], so an empty list
    # would create a pipeline that 500s (IndexError) on every query — reject at
    # the edge with 422 instead.
    knowledge_base_ids: List[str] = Field(..., min_length=1)
    retrieval_config: Dict[str, Any] = {}
    generation_config: Dict[str, Any] = {}


class RAGPipelineResponse(BaseModel):
    """RAG pipeline creation response (typed instead of a raw dict, #144)."""

    pipeline_id: str
    name: str
    knowledge_base_ids: List[str]
    created_at: str
    message: str = "RAG pipeline created successfully"


class QueryRequest(BaseModel):
    """Query request"""

    question: str
    top_k: int = 5
    conversation_id: Optional[
        str
    ] = None  # For conversational RAG - enables conversation history
    # Per-query generation-model override. None → use the KB's configured llm_model
    # (then the platform default). Lets a caller pick a specific model per question
    # (e.g. a coding/reasoning model on an external fleet) without reconfiguring the
    # KB. Does NOT affect embeddings — those must match the model used at ingest.
    llm_model: Optional[str] = None
    # standard | hyde | self_rag | auto (decision engine) | corrective (CRAG)
    method: str = "standard"
    # Orthogonal, capability-adaptive post-retrieval enhancers (apply to any method):
    rerank: bool = False  # re-rank sources (cross-encoder if available, else LLM)
    compress: bool = False  # contextual compression of the retrieved context
    # Retrieval strategy (#45): hybrid = dense + BM25 sparse (recall for keyword/rare
    # terms). Needs rank-bm25; falls back to dense if unavailable.
    hybrid: bool = False
    # parent_context (#45, small-to-big): match precise child chunks, but return each
    # with its neighbouring chunks (parent window) for fuller context. Takes
    # precedence over hybrid when both set.
    parent_context: bool = False

    @field_validator("method")
    @classmethod
    def _validate_method(cls, v: str) -> str:
        """Reject unknown methods with a 422 instead of silently running standard.

        Normalises case so callers may send e.g. "Self_RAG". Unknown values
        (typos, "raptor", "conversational", "parent_child", …) fail loudly with the
        valid set — the caller learns what they actually asked for. (#138)
        """
        normalized = (v or "standard").lower()
        if normalized not in VALID_RAG_METHODS:
            raise ValueError(
                f"invalid method '{v}'; valid values: {sorted(VALID_RAG_METHODS)}. "
                "(conversational RAG is enabled via conversation_id, not method; "
                "hybrid/parent_context are separate boolean flags.)"
            )
        return normalized


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
