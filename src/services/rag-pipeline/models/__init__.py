"""Pydantic request/response models for the RAG Pipeline API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from config import settings

# Canonical set of selectable generation/retrieval-rewrite strategies (the `method`
# field). "conversational" is NOT here — it is activated by passing `conversation_id`,
# not by `method`. Retrieval strategies (hybrid/parent_context) are separate boolean
# flags, not methods. Kept here (not in rag/runner) so the request model can reject an
# unknown method with a 422 at the API edge instead of silently coercing to standard.
VALID_RAG_METHODS = {"standard", "hyde", "self_rag", "auto", "corrective"}


class KnowledgeBaseCreate(BaseModel):
    """Knowledge base creation request"""

    name: str = Field(..., min_length=1)
    # Optional — a description shouldn't be required to create a KB (#144).
    description: str = ""
    embedding_model: str = settings.OLLAMA_EMBEDDING_MODEL
    llm_model: str = settings.OLLAMA_LLM_MODEL
    # Chunking bounds: reject non-positive/absurd sizes at the edge instead of
    # letting them reach the splitter (a 0/negative size or overlap >= size makes
    # the text splitter loop forever or emit degenerate chunks).
    chunk_size: int = Field(512, ge=1, le=8192)
    chunk_overlap: int = Field(50, ge=0, le=8192)

    @model_validator(mode="after")
    def _overlap_below_size(self) -> "KnowledgeBaseCreate":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be smaller than "
                f"chunk_size ({self.chunk_size})"
            )
        return self


class KnowledgeBaseUpdate(BaseModel):
    """Partial update of a knowledge base's mutable metadata (PATCH).

    Only name / description / llm_model. `embedding_model` and the chunking
    params are intentionally NOT updatable: changing the embedding model would
    invalidate every stored vector (they'd need full re-ingestion), and the
    chunk sizes only apply at ingest time — editing them post-hoc would silently
    desync the stored chunks from the declared config. Rename / re-describe /
    swap the generation model without touching the Qdrant collection.
    """

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    llm_model: Optional[str] = None


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


class RAGPipelineInfo(BaseModel):
    """RAG pipeline list/get response (#426) -- separate from RAGPipelineResponse
    since that one carries a creation-only `message` field and uses `pipeline_id`
    where the internal `state.rag_pipelines` dict (and Postgres row) key is `id`;
    reusing it for list/get would either show a stale "created successfully"
    message on every entry or require remapping the dict key on every read."""

    id: str
    name: str
    knowledge_base_ids: List[str]
    created_at: str


class MetadataFilter(BaseModel):
    """Restrict retrieval to chunks matching these fields (docs/rag-methods.md
    Bucket 1 — moved there from Bucket 2 once shipped). Fields left as None
    are not filtered; multiple set fields are ANDed. Limited to what's
    actually stamped on every chunk at
    ingest time (routes/rag.py's upload_document) -- there's no user-settable
    tag/label mechanism yet, so filtering by anything beyond these two would
    need a separate ingest-time change first."""

    source: Optional[str] = None  # exact filename match, e.g. "handbook.pdf"
    document_id: Optional[str] = None  # exact match — scope to one upload


class QueryRequest(BaseModel):
    """Query request"""

    question: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=100)
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
    # Metadata filtering: restrict retrieval to chunks matching source/document_id.
    # Orthogonal to method/hybrid/parent_context — applies to whichever retrieval
    # strategy runs.
    metadata_filter: Optional[MetadataFilter] = None

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
    document_id: str


class DocumentInfo(BaseModel):
    """A single uploaded document within a knowledge base (#427) -- aggregated
    from its chunks' Qdrant payloads, not a separate stored record. `document_id`
    is a per-upload UUID stamped on every chunk since #427; chunks uploaded
    before that (no `document_id` in their payload) are grouped by `filename`
    instead, with `document_id` synthesized as `legacy:<filename>` -- see
    `_group_documents` in routes/rag.py for exactly how that fallback works."""

    document_id: str
    filename: str
    chunk_count: int
    uploaded_at: Optional[str] = None
