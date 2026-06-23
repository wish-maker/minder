"""
Self-RAG Pipeline

Implements Self-Refinement RAG with quality-based iterative improvement.
Generates answers, evaluates quality, and refines if needed.

This is a domain component with NO external dependencies on infrastructure.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class SelfRAGPipeline:
    """
    Self-RAG with quality-based refinement (RPi 4 optimized)

    Implements iterative self-refinement loop:
    1. Generate initial answer from context
    2. Evaluate answer quality (relevance, accuracy, hallucination)
    3. Refine if quality below threshold
    4. Repeat until quality threshold met or max iterations reached

    Features:
    - Quality-aware generation with threshold checking
    - Hallucination detection and context reduction
    - Lazy-loaded quality evaluator
    - Configurable iteration limits

    Attributes:
        max_iterations (int): Maximum refinement iterations
        quality_threshold (float): Minimum quality score (0.0-1.0)
        evaluator (QualityEvaluator): Lazy-loaded evaluator instance

    Example:
        >>> pipeline = SelfRAGPipeline(max_iterations=2, quality_threshold=0.7)
        >>> result = await pipeline.generate_with_self_refinement(
        ...     question="What is RAG?",
        ...     context="RAG is...",
        ...     sources=[...],
        ...     llm_manager=manager
        ... )
        >>> print(f"Answer quality: {result['quality']['threshold_met']}")
    """

    def __init__(self, max_iterations: int = 2, quality_threshold: float = 0.7):
        """
        Initialize Self-RAG pipeline

        Args:
            max_iterations: Maximum refinement iterations (1-5 recommended)
            quality_threshold: Minimum quality score to accept (0.0-1.0)

        Raises:
            ValueError: If parameters invalid
        """
        if max_iterations <= 0:
            raise ValueError(f"max_iterations must be positive, got {max_iterations}")

        if not 0 <= quality_threshold <= 1:
            raise ValueError(
                f"quality_threshold must be in [0, 1], got {quality_threshold}"
            )

        self.max_iterations = max_iterations
        self.quality_threshold = quality_threshold
        self.evaluator = None
        self._evaluator_loaded = False

        logger.info(
            f"✅ SelfRAGPipeline initialized: max_iterations={max_iterations}, "
            f"quality_threshold={quality_threshold}"
        )

    def _load_evaluator(self) -> None:
        """
        Lazy load quality evaluator

        Loads evaluator on first use to avoid startup overhead.
        Sets flag to prevent retry on failure.
        """
        if not self._evaluator_loaded:
            try:
                from quality_evaluator import get_advanced_evaluator

                self.evaluator = get_advanced_evaluator()
                self._evaluator_loaded = True
                logger.info("✅ Quality evaluator loaded for Self-RAG")

            except Exception as e:
                logger.warning(f"⚠️ Failed to load quality evaluator: {e}")
                self._evaluator_loaded = True  # Don't retry

    async def generate_with_self_refinement(
        self,
        question: str,
        context: str,
        sources: List[Dict[str, Any]],
        llm_manager: Any,
        model: str = "llama3",
    ) -> Dict[str, Any]:
        """
        Generate answer with self-refinement loop

        Iteratively generates and evaluates answers until quality threshold
        is met or max iterations reached.

        Args:
            question: User question
            context: Retrieved context for answer generation
            sources: Source documents for evaluation
            llm_manager: LLM manager for answer generation
            model: LLM model name

        Returns:
            Dict with keys:
                answer (str): Generated answer text
                quality (Dict): Quality metrics including:
                    iterations (int): Number of iterations performed
                    threshold_met (bool): Whether quality threshold was met

        Raises:
            ValueError: If question or context empty
        """
        if not question:
            raise ValueError("question cannot be empty")

        if not context:
            raise ValueError("context cannot be empty")

        if not sources:
            logger.warning("No sources provided for quality evaluation")

        # Load evaluator on first use
        self._load_evaluator()

        current_answer = None
        current_context = context
        iteration = 0

        logger.info(f"🔄 Starting Self-RAG with max {self.max_iterations} iterations")

        for iteration in range(self.max_iterations):
            # Generate answer
            result = await llm_manager.generate_response(
                prompt=question, context=current_context, model=model
            )

            current_answer = result["text"]

            # Skip quality evaluation if evaluator not available
            if self.evaluator is None:
                logger.info("ℹ️ Quality evaluator unavailable, using first iteration")
                break

            # Evaluate quality
            try:
                quality_result = self.evaluator.evaluate_answer_quality(
                    question=question,
                    answer=current_answer,
                    context=current_context,
                    context_sources=sources,
                )

                overall_quality = quality_result.get("overall_quality", 0.0)
                logger.info(
                    f"🔄 Iteration {iteration + 1}: Quality = {overall_quality:.3f}"
                )

                # Check if quality is sufficient
                if overall_quality >= self.quality_threshold:
                    logger.info(
                        f"✅ Quality threshold met: {overall_quality:.3f} >= "
                        f"{self.quality_threshold}"
                    )
                    break

                # Refine context if quality is low
                if iteration < self.max_iterations - 1:
                    hallucination_result = quality_result.get("hallucination", {})

                    if hallucination_result.get("is_hallucination"):
                        logger.warning("⚠️ Hallucination detected, reducing context")
                        # Reduce context to top sources only
                        current_context = "\n".join(
                            [s.get("text", "") for s in sources[:2]]
                        )

            except Exception as e:
                logger.warning(f"⚠️ Quality evaluation failed: {e}")
                break

        logger.info(f"✅ Self-RAG completed after {iteration + 1} iterations")

        return {
            "answer": current_answer,
            "quality": {
                "iterations": iteration + 1,
                "threshold_met": iteration < self.max_iterations,
            },
        }
