"""Query orchestration for the RAG pipeline.

``run_query`` runs the full flow — method selection, retrieval (optionally HyDE-rewritten),
conversation context, generation (standard or Self-RAG), and conversation persistence —
and returns a plain dict of response fields. It depends only on the objects passed in via
``RagComponents``; it never imports the service entrypoint, so the import graph stays acyclic.
"""

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from models import (
    VALID_RAG_METHODS,  # single source of truth (also enforced at the edge)
)
from rag.methods import compress as compress_method
from rag.methods import corrective as corrective_method
from rag.methods import decision as decision_method
from rag.methods import hyde as hyde_method
from rag.methods import rerank as rerank_method
from rag.methods import self_rag as self_rag_method

logger = logging.getLogger(__name__)

# Conversational RAG is single-user today (see #45 / TODO in conversation repo).
_DEFAULT_USER = "default"
_MAX_TURNS = 3


class GenerationError(Exception):
    """The LLM failed to produce the final answer. The runner stays HTTP-agnostic;
    the query route maps this to a 503 instead of returning the error as a 200
    "answer" (#232) — mirroring how embedding failures already 503 (#77)."""


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
    # Human-readable notes about anything the caller asked for that quietly did NOT
    # happen (component missing, empty result, precedence). Surfaced as
    # method_details.degraded so a client can detect a downgrade without diffing (#138).
    degraded: List[str] = []

    # method=auto: let the decision engine choose. It decides more than HyDE/Self-RAG
    # (top_k, reranking, retrieval strategy); the runner now applies the parts it can
    # control here rather than discarding them (#139).
    auto_top_k: Optional[int] = None
    auto_rerank = False
    if method == "auto":
        use_hyde, use_self_rag, dec = await decision_method.route(
            question, components.decision_engine
        )
        if dec:
            details["decision"] = dec
            auto_top_k = dec.get("top_k")
            auto_rerank = bool(dec.get("use_reranking"))
            # The retriever (dense/hybrid/parent) is selected per-request upstream in
            # the route and can't be swapped in the runner — so a non-dense strategy
            # the engine picks is advisory only. Say so instead of pretending (#139).
            strat = dec.get("retrieval_strategy")
            if strat and strat not in ("basic", "dense"):
                degraded.append(
                    f"auto: engine suggested retrieval_strategy={strat!r}, but the "
                    "retriever is chosen per-request (hybrid/parent_context flags) — "
                    "not auto-switched"
                )
        else:
            degraded.append(
                "auto: decision engine unavailable — used standard retrieval/generation"
            )
        details["requested"] = "auto"

    # Effective retrieval depth: the engine's top_k in auto mode, else the request's.
    effective_top_k = auto_top_k if (method == "auto" and auto_top_k) else request.top_k

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
            degraded.append(
                "hyde: expander unavailable or empty rewrite — retrieved on raw query"
            )

    context_result = await components.retrieve(
        pipeline, retrieval_query, effective_top_k
    )

    # Corrective RAG: grade the retrieval and re-retrieve with a refined query if weak.
    if method == "corrective":
        context_result, corr_details = await corrective_method.correct(
            question,
            context_result,
            components.corrective_pipeline,
            components.retrieve,
            pipeline,
            effective_top_k,
            components.ollama_manager,
            llm_model,
        )
        if corr_details:
            details["corrective"] = corr_details
        else:
            # Empty details = pipeline unavailable or it raised → nothing corrective ran.
            degraded.append(
                "corrective: pipeline unavailable — used standard retrieval (no grading)"
            )

    # Optional adaptive re-ranking (cross-encoder if available, else LLM). Orthogonal
    # to method — applies to whatever was retrieved above. In auto mode the decision
    # engine can also request it (#139).
    if getattr(request, "rerank", False) or auto_rerank:
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
                # Evaluator absent → a single pass ran, not true self-refinement.
                # Say so instead of letting method="self_rag" imply refinement (#138).
                if not quality.get("evaluated"):
                    degraded.append(
                        "self_rag: quality evaluator unavailable — single pass, "
                        "no refinement"
                    )
            else:
                use_self_rag = False  # fell back
                degraded.append(
                    "self_rag: pipeline unavailable or errored — used standard generation"
                )

        if not answer_text:  # standard path (default or any fallback above)
            # Thread the resolved generation model through — the standard path was the
            # only one that dropped it, so every query silently used the default model
            # regardless of the KB/pipeline/per-query llm_model. generation_config wins
            # if it explicitly sets "model" (merged into one dict → no kwarg collision).
            gen_kwargs = {"model": llm_model, **(generation_config or {})}
            answer_result = await components.ollama_manager.generate_response(
                prompt=question, context=combined_context, **gen_kwargs
            )
            if answer_result.get("error"):
                raise GenerationError(
                    answer_result.get("text", "LLM generation failed")
                )
            answer_text = answer_result["text"]
            model_used = answer_result.get("model", llm_model)
            tokens_used = answer_result.get("tokens_used")

    if method == "auto":
        # Report "auto" honestly (was previously relabeled to its sub-method); the
        # decision + what was applied live in method_details.decision (#139).
        effective_method = "auto"
        if details.get("decision"):
            details["decision"]["applied"] = {
                "hyde": use_hyde,
                "self_rag": use_self_rag,
                "top_k": effective_top_k,
                "rerank": bool(getattr(request, "rerank", False) or auto_rerank),
            }
    elif method == "corrective":
        # Only claim "corrective" if grading actually ran (details recorded). If the
        # pipeline was unavailable the grade never happened → report standard (#138).
        effective_method = "corrective" if details.get("corrective") else "standard"
    else:
        effective_method = (
            "self_rag" if use_self_rag else "hyde" if use_hyde else "standard"
        )

    if degraded:
        details["degraded"] = degraded

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
