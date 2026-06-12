"""
Retrieval Service

Orchestrates document retrieval using domain components and infrastructure.
Manages the complete retrieval pipeline with resource management.

This is a service layer component that orchestrates domain + infrastructure.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    Document retrieval orchestration service

    Coordinates the complete retrieval pipeline:
    1. Resource throttling (RPi 4 optimization)
    2. Query embedding generation
    3. HyDE query expansion (optional)
    4. Multi-KB hybrid search
    5. Cross-encoder re-ranking (optional)
    6. CRAG fallback (optional)
    7. Parent-child enhancement (optional)
    8. Context compression

    Features:
    - Resource-aware retrieval
    - Multi-strategy search (HyDE, hybrid, re-ranking)
    - Fallback mechanisms (CRAG, semantic-only)
    - Context optimization (compression, parent-child)

    Attributes:
        ollama_manager: LLM and embedding service
        qdrant_client: Vector database client
        resource_manager: RPi 4 resource manager
        hyde_expander: HyDE query expansion (optional)
        hybrid_searcher: Hybrid search (optional)
        reranker: Cross-encoder re-ranker (optional)
        crag_retriever: CRAG fallback (optional)
        parent_child_retriever: Parent-child enhancement (optional)
        context_compressor: Context compression (optional)

    Example:
        >>> service = RetrievalService(
        ...     ollama_manager=ollama,
        ...     qdrant_client=qdrant,
        ...     resource_manager=pi4_mgr
        ... )
        >>> results = await service.retrieve(
        ...     pipeline=pipeline_dict,
        ...     question="What is RAG?",
        ...     top_k=5
        ... )
    """

    def __init__(
        self,
        ollama_manager: Any,
        qdrant_client: Any,
        resource_manager: Any,
        hyde_expander: Any = None,
        hybrid_searcher: Any = None,
        reranker: Any = None,
        crag_retriever: Any = None,
        parent_child_retriever: Any = None,
        context_compressor: Any = None,
    ):
        """
        Initialize retrieval service

        Args:
            ollama_manager: LLM and embedding service
            qdrant_client: Vector database client
            resource_manager: Resource throttling manager
            hyde_expander: Optional HyDE query expander
            hybrid_searcher: Optional hybrid search retriever
            reranker: Optional cross-encoder re-ranker
            crag_retriever: Optional CRAG fallback retriever
            parent_child_retriever: Optional parent-child retriever
            context_compressor: Optional context compressor

        Note:
            All domain components are optional - service uses what's available
        """
        self.ollama_manager = ollama_manager
        self.qdrant_client = qdrant_client
        self.resource_manager = resource_manager
        self.hyde_expander = hyde_expander
        self.hybrid_searcher = hybrid_searcher
        self.reranker = reranker
        self.crag_retriever = crag_retriever
        self.parent_child_retriever = parent_child_retriever
        self.context_compressor = context_compressor

        logger.info("✅ RetrievalService initialized")

    async def retrieve(
        self,
        pipeline: Dict[str, Any],
        question: str,
        top_k: int,
        knowledge_bases: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Retrieve relevant documents with full pipeline orchestration

        Args:
            pipeline: Pipeline configuration with knowledge_base_ids
            question: User question
            top_k: Number of results to return
            knowledge_bases: Knowledge base metadata dictionary

        Returns:
            Dict with keys:
                context (str): Compressed context string
                sources (List[Dict]): Source documents with metadata

        Raises:
            ValueError: If question empty or pipeline invalid
        """
        if not question:
            raise ValueError("question cannot be empty")

        if not pipeline or "knowledge_base_ids" not in pipeline:
            raise ValueError("pipeline must contain knowledge_base_ids")

        if not pipeline["knowledge_base_ids"]:
            raise ValueError("pipeline must have at least one knowledge base")

        logger.info(f"🔄 Starting retrieval for: {question[:50]}...")

        # Throttle if resources constrained
        await self.resource_manager.throttle_if_needed()

        # Use semaphore to limit concurrent requests
        async with self.resource_manager.request_semaphore:
            # Get embedding model from first KB
            first_kb_id = pipeline["knowledge_base_ids"][0]
            embed_model = knowledge_bases[first_kb_id]["embedding_model"]

            # Create query embedding
            question_embeddings = await self.ollama_manager.generate_embeddings(
                [question],
                model=embed_model
            )
            question_embedding = question_embeddings[0]

            # Execute retrieval pipeline
            all_results = await self._execute_search(
                pipeline, question, question_embedding, top_k, embed_model
            )

            # Apply enhancements
            enhanced_results = await self._apply_enhancements(
                all_results, pipeline, question, top_k, knowledge_bases
            )

            # Compress context
            compressed_context = self._compress_context(question, enhanced_results)

            logger.info(f"✅ Retrieval completed: {len(enhanced_results)} sources")

            return {
                "context": compressed_context,
                "sources": enhanced_results,
            }

    async def _execute_search(
        self,
        pipeline: Dict[str, Any],
        question: str,
        question_embedding: List[float],
        top_k: int,
        embed_model: str
    ) -> List[Any]:
        """
        Execute search across knowledge bases with HyDE and hybrid search

        Args:
            pipeline: Pipeline configuration
            question: User question
            question_embedding: Query embedding vector
            top_k: Number of results
            embed_model: Embedding model name

        Returns:
            List of search results (points or dicts)
        """
        all_results = []
        hyde_results = []

        # Apply HyDE query expansion if available
        if self.hyde_expander:
            hyde_results = await self._hyde_search(
                pipeline, question, question_embedding, top_k, embed_model
            )

        # Search across all knowledge bases
        for kb_id in pipeline["knowledge_base_ids"]:
            try:
                search_result = self.qdrant_client.query_points(
                    collection_name=kb_id,
                    query=question_embedding,
                    limit=top_k * 2
                )

                # Try hybrid search if index available
                if self.hybrid_searcher and kb_id in self.hybrid_searcher.sparse_index:
                    hybrid_results = await self.hybrid_searcher.hybrid_search(
                        kb_id, question_embedding, question, search_result.points, top_k
                    )
                    # Convert hybrid results back to point objects
                    for doc_id, hybrid_score in hybrid_results:
                        for point in search_result.points:
                            if point.id == doc_id or point.payload.get("_id") == doc_id:
                                point.score = hybrid_score
                                all_results.append(point)
                                break
                else:
                    all_results.extend(search_result.points)

            except Exception as e:
                logger.warning(f"⚠️ Search failed for KB {kb_id}: {e}")

        # Combine with HyDE results
        if hyde_results:
            logger.info(
                f"🔄 Combining {len(hyde_results)} HyDE results with "
                f"{len(all_results)} original results"
            )
            for hyde_point in hyde_results:
                hyde_point.score = hyde_point.score * 1.1  # 10% boost
                all_results.append(hyde_point)

        # Sort by score and take top_k * 2 for re-ranking
        all_results = sorted(all_results, key=lambda x: x.score, reverse=True)[:top_k * 2]

        return all_results

    async def _hyde_search(
        self,
        pipeline: Dict[str, Any],
        question: str,
        question_embedding: List[float],
        top_k: int,
        embed_model: str
    ) -> List[Any]:
        """
        Execute HyDE query expansion and search

        Args:
            pipeline: Pipeline configuration
            question: User question
            question_embedding: Original query embedding
            top_k: Number of results
            embed_model: Embedding model name

        Returns:
            List of HyDE search results
        """
        try:
            hyde_expansion = await self.hyde_expander.expand_query(
                question, self.ollama_manager, embed_model, question_embedding
            )

            if not hyde_expansion.get("expanded"):
                return []

            logger.info("🔄 Using HyDE query expansion")

            # Search with hypothetical embedding
            hyde_results = []
            for kb_id in pipeline["knowledge_base_ids"]:
                try:
                    hyde_search = self.qdrant_client.query_points(
                        collection_name=kb_id,
                        query=hyde_expansion["hypothetical_embedding"],
                        limit=top_k
                    )
                    hyde_results.extend(hyde_search.points)
                except Exception as e:
                    logger.warning(f"⚠️ HyDE search failed for KB {kb_id}: {e}")

            return hyde_results

        except Exception as e:
            logger.warning(f"⚠️ HyDE expansion failed: {e}")
            return []

    async def _apply_enhancements(
        self,
        all_results: List[Any],
        pipeline: Dict[str, Any],
        question: str,
        top_k: int,
        knowledge_bases: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Apply re-ranking, CRAG, and parent-child enhancements

        Args:
            all_results: Search results to enhance
            pipeline: Pipeline configuration
            question: User question
            top_k: Number of results
            knowledge_bases: Knowledge base metadata

        Returns:
            Enhanced results as list of dicts
        """
        # Apply cross-encoder re-ranking
        all_results = await self._apply_reranking(all_results, question, top_k)

        # Apply CRAG fallback if quality poor
        if self.crag_retriever:
            all_results = await self._apply_crag(
                all_results, pipeline, question, top_k
            )

        # Apply parent-child enhancement
        all_results = self._apply_parent_child(
            all_results, pipeline, knowledge_bases
        )

        # Convert to dict format
        context_sources = [
            {
                "text": r.payload.get("text", "") if hasattr(r, "payload") else r.get("text", ""),
                "source": r.payload.get("source", "") if hasattr(r, "payload") else r.get("source", ""),
                "score": r.score
            }
            for r in all_results
        ]

        return context_sources[:top_k]

    async def _apply_reranking(
        self,
        all_results: List[Any],
        question: str,
        top_k: int
    ) -> List[Any]:
        """
        Apply cross-encoder re-ranking

        Args:
            all_results: Search results to re-rank
            question: User question
            top_k: Number of results

        Returns:
            Re-ranked results
        """
        if not self.reranker:
            return all_results[:top_k]

        try:
            documents_for_rerank = [
                {"text": r.payload.get("text", ""), "score": r.score}
                for r in all_results
            ]
            reranked_docs = self.reranker.rerank(question, documents_for_rerank, top_k)

            # Reconstruct results with re-ranked scores
            reranked_results = []
            for doc, score in reranked_docs:
                for point in all_results:
                    if point.payload.get("text") == doc.get("text"):
                        point.score = score
                        reranked_results.append(point)
                        break

            logger.info(f"✅ Re-ranking applied: {len(reranked_results)} results")
            return reranked_results[:top_k]

        except Exception as e:
            logger.warning(f"⚠️ Re-ranking failed: {e}")
            return all_results[:top_k]

    async def _apply_crag(
        self,
        all_results: List[Any],
        pipeline: Dict[str, Any],
        question: str,
        max_results: int
    ) -> List[Any]:
        """
        Apply CRAG fallback if retrieval quality poor

        Args:
            all_results: Current search results
            pipeline: Pipeline configuration
            question: User question
            max_results: Maximum results to return

        Returns:
            Enhanced results with CRAG fallback if triggered
        """
        try:
            internal_results = [
                {"id": str(r.id), "text": r.payload.get("text", ""), "score": r.score}
                for r in all_results
            ]

            crag_result = await self.crag_retriever.retrieve_with_fallback(
                query=question,
                internal_results=internal_results,
                kb_id=pipeline["knowledge_base_ids"][0],
                max_results=max_results
            )

            if crag_result.get("fallback_used"):
                logger.info(
                    f"🌐 CRAG fallback applied: {crag_result['web_count']} web results"
                )

                # Convert CRAG results to point-like format
                crag_results = []
                for i, result in enumerate(crag_result.get("results", [])):
                    point_dict = {
                        "id": result.get("id", f"web_{i}"),
                        "text": result.get("text", ""),
                        "source": result.get("source", "web_search"),
                        "score": result.get("score", 0.7)
                    }
                    crag_results.append(point_dict)

                logger.info(f"✅ CRAG enhanced retrieval: {len(crag_results)} results")
                return crag_results

            return all_results

        except Exception as e:
            logger.warning(f"⚠️ CRAG fallback failed: {e}")
            return all_results

    def _apply_parent_child(
        self,
        all_results: List[Any],
        pipeline: Dict[str, Any],
        knowledge_bases: Dict[str, Dict[str, Any]]
    ) -> List[Any]:
        """
        Apply parent-child retrieval enhancement

        Args:
            all_results: Current search results
            pipeline: Pipeline configuration
            knowledge_bases: Knowledge base metadata

        Returns:
            Enhanced results with parent context
        """
        if not self.parent_child_retriever:
            return all_results

        try:
            first_kb_id = pipeline["knowledge_base_ids"][0]

            if not knowledge_bases[first_kb_id].get("parent_child_enabled", False):
                return all_results

            # Convert to dict format
            child_results = [
                {
                    "id": str(r.id),
                    "text": r.payload.get("text", ""),
                    "source": r.payload.get("source", ""),
                    "score": r.score
                }
                for r in all_results
            ]

            enhanced_results = self.parent_child_retriever.retrieve_with_parent_context(
                first_kb_id, child_results
            )

            logger.info(f"✅ Parent-child retrieval applied: {len(enhanced_results)} results")

            # Convert back to point format (simplified)
            return enhanced_results

        except Exception as e:
            logger.warning(f"⚠️ Parent-child retrieval failed: {e}")
            return all_results

    def _compress_context(self, question: str, context_sources: List[Dict[str, Any]]) -> str:
        """
        Compress context while preserving relevance

        Args:
            question: User question
            context_sources: Source documents

        Returns:
            Compressed context string
        """
        if not self.context_compressor:
            return "\n\n".join([ctx.get("text", "") for ctx in context_sources])

        try:
            compression_result = self.context_compressor.compress(question, context_sources)
            compressed_context = compression_result["compressed_context"]

            compression_ratio = (
                compression_result.get("compressed_length", 0) /
                max(compression_result.get("original_length", 1), 1)
            )

            logger.info(f"✅ Context compressed: {compression_ratio:.1%} ratio")
            return compressed_context

        except Exception as e:
            logger.warning(f"⚠️ Context compression failed: {e}")
            return "\n\n".join([ctx.get("text", "") for ctx in context_sources])
