"""Query orchestration for the RAG pipeline.

``run_query`` runs the full flow — method selection, retrieval (optionally HyDE-rewritten),
conversation context, generation (standard or Self-RAG), and conversation persistence —
and returns a plain dict of response fields. It depends only on the objects passed in via
``RagComponents``; it never imports the service entrypoint, so the import graph stays acyclic.
"""

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from rag.methods import compress as compress_method
from rag.methods import corrective as corrective_method
from rag.methods import decision as decision_method
from rag.methods import hyde as hyde_method
from rag.methods import rerank as rerank_method
from rag.methods import self_rag as self_rag_method

logger = logging.getLogger(__name__)

VALID_RAG_METHODS = {"standard", "hyde", "self_rag", "auto", "corrective"}

# Conversational RAG is single-user today (see #45 / TODO in conversation repo).
_DEFAULT_USER = "default"
_MAX_TURNS = 3


@dataclass
class RagComponents:
    """Everything the runner needs, injected by the caller (no globals imported)."""

    ollama_manager: Any
    retrieve: Callable[
        ..., Awaitable[Dict[str, Any]]
    ]  # (pipeline, query, top_k) -> dict
    hyde_expander: Any = None
    self_rag_pipeline: Any = None
    decision_engine: Any = None
    corrective_pipeline: Any = None
    reranker: Any = None
    compressor: Any = None
    conversation_repository: Any = None
    gen_timer: Any = None  # prometheus histogram (labels(...).time()) or None


async def _load_conversation_context(repo, conversation_id) -> str:
    if not (conversation_id and repo):
        return ""
    try:
        ctx = await repo.build_context(
            user_id=_DEFAULT_USER, conversation_id=conversation_id, max_turns=_MAX_TURNS
        )
        if ctx:
            logger.info(f"🔄 Loaded conversation context for {conversation_id}")
        return ctx or ""
    except Exception as e:
        logger.warning(f"⚠️  Failed to load conversation context: {e}")
        return ""


async def _store_conversation_turn(
    repo,
    conversation_id,
    pipeline_id,
    question,
    answer,
    model_used,
    sources_count,
    method,
) -> None:
    if not (conversation_id and repo):
        return
    try:
        await repo.store_turn(
            user_id=_DEFAULT_USER,
            conversation_id=conversation_id,
            question=question,
            answer=answer,
            metadata={
                "pipeline_id": pipeline_id,
                "model_used": model_used,
                "sources_count": sources_count,
                "method": method,
                "timestamp": None,  # set by DB default
            },
        )
        logger.info(f"💾 Stored conversation turn for {conversation_id}")
    except Exception as e:
        logger.warning(f"⚠️  Failed to store conversation turn: {e}")


async def run_query(
    *,
    pipeline: Dict[str, Any],
    pipeline_id: str,
    request: Any,
    llm_model: str,
    generation_config: Optional[Dict[str, Any]],
    components: RagComponents,
) -> Dict[str, Any]:
    """Execute one RAG query. Returns a dict of QueryResponse fields."""
    question = request.question
    method = (getattr(request, "method", None) or "standard").lower()
    if method not in VALID_RAG_METHODS:
        method = "standard"

    use_hyde = method == "hyde"
    use_self_rag = method == "self_rag"
    details: Dict[str, Any] = {}

    # method=auto: let the decision engine choose.
    if method == "auto":
        use_hyde, use_self_rag, dec = await decision_method.route(
            question, components.decision_engine
        )
        if dec:
            details["decision"] = dec
        details["requested"] = "auto"

    # HyDE: retrieve using a hypothetical answer rather than the raw question.
    retrieval_query = question
    if use_hyde:
        hypothetical = await hyde_method.rewrite_query(
            question, components.hyde_expander, components.ollama_manager, llm_model
        )
        if hypothetical:
            retrieval_query = hypothetical
            details["hyde"] = {"hypothetical_chars": len(hypothetical)}
        else:
            use_hyde = False

    context_result = await components.retrieve(pipeline, retrieval_query, request.top_k)

    # Corrective RAG: grade the retrieval and re-retrieve with a refined query if weak.
    if method == "corrective":
        context_result, corr_details = await corrective_method.correct(
            question,
            context_result,
            components.corrective_pipeline,
            components.retrieve,
            pipeline,
            request.top_k,
            components.ollama_manager,
            llm_model,
        )
        if corr_details:
            details["corrective"] = corr_details

    # Optional adaptive re-ranking (cross-encoder if available, else LLM). Orthogonal
    # to method — applies to whatever was retrieved above.
    if getattr(request, "rerank", False):
        context_result, rr_details = await rerank_method.apply(
            question,
            context_result,
            components.reranker,
            components.ollama_manager,
            llm_model,
        )
        details.update(rr_details)

    # Optional contextual compression of the retrieved context before generation.
    if getattr(request, "compress", False):
        context_result, cc_details = compress_method.apply(
            question, context_result, components.compressor
        )
        details.update(cc_details)

    # Conversational RAG context.
    conv = await _load_conversation_context(
        components.conversation_repository, getattr(request, "conversation_id", None)
    )
    combined_context = ""
    if conv:
        combined_context = f"Previous conversation:\n{conv}\n\n"
    if context_result["context"]:
        combined_context += f"Relevant documents:\n{context_result['context']}"

    # Generation: Self-RAG refinement, else a standard single pass.
    answer_text = None
    model_used = llm_model
    tokens_used = None

    def _timer():
        if components.gen_timer is not None:
            return components.gen_timer.labels(model=llm_model).time()

        class _Null:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Null()

    with _timer():
        if use_self_rag:
            answer_text, quality = await self_rag_method.generate(
                components.self_rag_pipeline,
                question,
                combined_context or context_result["context"],
                context_result.get("sources", []),
                components.ollama_manager,
                llm_model,
            )
            if answer_text:
                details["self_rag"] = quality
            else:
                use_self_rag = False  # fell back

        if not answer_text:  # standard path (default or any fallback above)
            answer_result = await components.ollama_manager.generate_response(
                prompt=question, context=combined_context, **(generation_config or {})
            )
            answer_text = answer_result["text"]
            model_used = answer_result.get("model", llm_model)
            tokens_used = answer_result.get("tokens_used")

    if method == "corrective":
        effective_method = "corrective"
    else:
        effective_method = (
            "self_rag" if use_self_rag else "hyde" if use_hyde else "standard"
        )

    await _store_conversation_turn(
        components.conversation_repository,
        getattr(request, "conversation_id", None),
        pipeline_id,
        question,
        answer_text,
        model_used,
        len(context_result.get("sources", [])),
        effective_method,
    )

    # Confidence = mean retrieval similarity of the sources actually used (Qdrant
    # cosine score from retrieve_relevant_documents), not a hardcoded constant.
    scores = [
        s["score"]
        for s in context_result.get("sources", [])
        if isinstance(s.get("score"), (int, float))
    ]
    confidence = round(sum(scores) / len(scores), 3) if scores else 0.0

    return {
        "answer": answer_text,
        "sources": context_result["sources"],
        "confidence": confidence,
        "model_used": model_used,
        "tokens_used": tokens_used,
        "method": effective_method,
        "method_details": details or None,
    }
