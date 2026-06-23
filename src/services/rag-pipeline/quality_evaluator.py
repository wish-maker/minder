"""
Advanced Quality Evaluator for Self-RAG

Provides production-ready quality metrics:
- Semantic similarity (sentence-transformers)
- BERTScore (factual correctness)
- Hallucination detection
- Answer coherence and completeness
"""

import logging
from typing import Any, Dict, List, Optional

# Optional dependencies for advanced metrics
try:
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.util import cos_sim

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning(
        "sentence-transformers not available. Install with: pip install sentence-transformers"
    )

try:
    from bert_score import BERTScorer

    BERTSCORE_AVAILABLE = True
except ImportError:
    BERTSCORE_AVAILABLE = False
    logging.warning("bert-score not available. Install with: pip install bert-score")

logger = logging.getLogger(__name__)


class AdvancedQualityEvaluator:
    """Advanced quality metrics for Self-RAG"""

    def __init__(
        self,
        semantic_model: str = "sentence-transformers/all-MiniLM-L-6-v2",
        bertscore_model: str = "microsoft/deberta-xlarge-mnli",
        use_gpu: bool = False,
    ):
        """
        Initialize advanced quality evaluator

        Args:
            semantic_model: Sentence transformer model for semantic similarity
            bertscore_model: BERTScore model for factual correctness
            use_gpu: Whether to use GPU acceleration
        """
        self.semantic_model_name = semantic_model
        self.bertscore_model_name = bertscore_model
        self.use_gpu = use_gpu

        # Lazy initialization (load models only when needed)
        self._semantic_model = None
        self._bertscore_model = None

        logger.info(
            f"✅ Advanced Quality Evaluator initialized (semantic: {semantic_model}, bertscore: {bertscore_model})"
        )

    @property
    def semantic_model(self) -> Optional[SentenceTransformer]:
        """Lazy load semantic model"""
        if self._semantic_model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                logger.info(f"🔄 Loading semantic model: {self.semantic_model_name}")
                self._semantic_model = SentenceTransformer(self.semantic_model_name)
                logger.info("✅ Semantic model loaded")
            except Exception as e:
                logger.warning(f"⚠️  Failed to load semantic model: {e}")
                self._semantic_model = False
        return self._semantic_model

    @property
    def bertscore_model(self) -> Optional[BERTScorer]:
        """Lazy load BERTScore model"""
        if self._bertscore_model is None and BERTSCORE_AVAILABLE:
            try:
                logger.info(f"🔄 Loading BERTScore model: {self.bertscore_model_name}")
                self._bertscore_model = BERTScorer(
                    model_type=[self.bertscore_model_name],
                    num_layers=(
                        len(self.bertscore_model_name)
                        if isinstance(self.bertscore_model_name, list)
                        else None
                    ),
                    idf=False,
                    device="cuda" if self.use_gpu else "cpu",
                    lang="en",
                )
                logger.info("✅ BERTScore model loaded")
            except Exception as e:
                logger.warning(f"⚠️  Failed to load BERTScore model: {e}")
                self._bertscore_model = False
        return self._bertscore_model

    def evaluate_semantic_similarity(
        self, answer: str, context: str, context_sources: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate semantic similarity between answer and context

        Args:
            answer: Generated answer
            context: Context text
            context_sources: Optional list of context sources for finer-grained comparison

        Returns:
            Dict with similarity metrics
        """
        if not self.semantic_model or self.semantic_model is False:
            logger.warning("⚠️  Semantic model not available, using basic metric")
            return self._basic_semantic_similarity(answer, context)

        try:
            # Encode answer and context
            answer_embedding = self.semantic_model.encode(answer)
            context_embedding = self.semantic_model.encode(context)

            # Calculate cosine similarity
            similarity = float(cos_sim(answer_embedding, context_embedding)[0][0])

            # If context sources available, calculate max similarity with any source
            max_source_similarity = similarity
            if context_sources:
                source_texts = [
                    s.get("text", "") for s in context_sources if s.get("text")
                ]
                if source_texts:
                    source_embeddings = self.semantic_model.encode(source_texts)
                    source_similarities = cos_sim(answer_embedding, source_embeddings)[
                        0
                    ]
                    max_source_similarity = float(max(source_similarities))

            result = {
                "similarity": similarity,
                "max_source_similarity": max_source_similarity,
                "normalized_similarity": (similarity + 1)
                / 2,  # Convert [-1, 1] to [0, 1]
                "confidence": (
                    "high"
                    if similarity > 0.7
                    else "medium" if similarity > 0.4 else "low"
                ),
            }

            logger.info(
                f"📊 Semantic similarity: {similarity:.3f} (max source: {max_source_similarity:.3f})"
            )
            return result

        except Exception as e:
            logger.warning(f"⚠️  Semantic similarity evaluation failed: {e}")
            return self._basic_semantic_similarity(answer, context)

    def _basic_semantic_similarity(self, answer: str, context: str) -> Dict[str, Any]:
        """Basic word overlap similarity as fallback"""
        answer_words = set(answer.lower().split())
        context_words = set(context.lower().split())

        if not context_words:
            return {
                "similarity": 0.0,
                "max_source_similarity": 0.0,
                "normalized_similarity": 0.0,
                "confidence": "low",
            }

        # Jaccard similarity
        intersection = answer_words & context_words
        union = answer_words | context_words
        jaccard = len(intersection) / len(union) if union else 0.0

        # Word overlap ratio
        overlap_ratio = len(intersection) / len(answer_words) if answer_words else 0.0

        # Combined score
        similarity = (jaccard + overlap_ratio) / 2

        return {
            "similarity": similarity,
            "max_source_similarity": similarity,
            "normalized_similarity": similarity,
            "confidence": (
                "high" if similarity > 0.5 else "medium" if similarity > 0.2 else "low"
            ),
            "fallback": "basic_word_overlap",
        }

    def evaluate_bertscore(
        self, answer: str, reference: str, language: str = "en"
    ) -> Dict[str, Any]:
        """
        Evaluate factual correctness using BERTScore

        Args:
            answer: Generated answer
            reference: Reference text (context or source)
            language: Language code

        Returns:
            Dict with BERTScore metrics
        """
        if not self.bertscore_model or self.bertscore_model is False:
            logger.warning("⚠️  BERTScore model not available, using basic metric")
            return self._basic_factual_score(answer, reference)

        try:
            # Calculate BERTScore
            P, R, F1 = self.bertscore_model.score(
                [answer], [reference], batch_size=1, verbose=False
            )

            result = {
                "precision": float(P[0]),
                "recall": float(R[0]),
                "f1": float(F1[0]),
                "confidence": "high" if F1 > 0.85 else "medium" if F1 > 0.7 else "low",
            }

            logger.info(
                f"📊 BERTScore F1: {result['f1']:.3f} (P: {result['precision']:.3f}, R: {result['recall']:.3f})"
            )
            return result

        except Exception as e:
            logger.warning(f"⚠️  BERTScore evaluation failed: {e}")
            return self._basic_factual_score(answer, reference)

    def _basic_factual_score(self, answer: str, reference: str) -> Dict[str, Any]:
        """Basic factual score as fallback"""
        answer_words = set(answer.lower().split())
        reference_words = set(reference.lower().split())

        if not reference_words:
            return {
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "confidence": "low",
                "fallback": "basic_word_overlap",
            }

        # Precision: How many answer words are in reference
        intersection = answer_words & reference_words
        precision = len(intersection) / len(answer_words) if answer_words else 0.0

        # Recall: How many reference words are covered by answer
        recall = len(intersection) / len(reference_words)

        # F1 score
        f1 = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "confidence": "high" if f1 > 0.7 else "medium" if f1 > 0.4 else "low",
            "fallback": "basic_word_overlap",
        }

    def evaluate_hallucination(
        self, answer: str, context: str, context_sources: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Detect potential hallucinations in the answer

        Args:
            answer: Generated answer
            context: Context text
            context_sources: Optional list of context sources

        Returns:
            Dict with hallucination metrics
        """
        try:
            hallucination_indicators = []
            hallucination_score = 0.0

            # Check 1: Answer is much shorter than expected
            if len(answer) < 50:
                hallucination_indicators.append("very_short_answer")
                hallucination_score += 0.3

            # Check 2: Contains uncertainty markers
            uncertainty_markers = [
                "maybe",
                "perhaps",
                "possibly",
                "might be",
                "could be",
                "not sure",
                "uncertain",
                "unknown",
                "???",
            ]
            answer_lower = answer.lower()
            found_markers = [
                marker for marker in uncertainty_markers if marker in answer_lower
            ]
            if found_markers:
                hallucination_indicators.append(f"uncertainty_markers: {found_markers}")
                hallucination_score += 0.2 * len(found_markers)

            # Check 3: Semantic similarity is very low
            semantic_result = self.evaluate_semantic_similarity(answer, context)
            if semantic_result["similarity"] < 0.3:
                hallucination_indicators.append("low_semantic_similarity")
                hallucination_score += 0.3

            # Check 4: Generic/vague phrases
            generic_phrases = [
                "it depends",
                "various factors",
                "multiple reasons",
                "in general",
                "typically",
                "usually",
            ]
            found_generic = [
                phrase for phrase in generic_phrases if phrase in answer_lower
            ]
            if found_generic:
                hallucination_indicators.append(f"generic_phrases: {found_generic}")
                hallucination_score += 0.1 * len(found_generic)

            # Check 5: No factual claims
            if not any(
                word in answer_lower
                for word in ["is", "are", "was", "were", "will be", "has", "have"]
            ):
                hallucination_indicators.append("no_factual_claims")
                hallucination_score += 0.2

            # Normalize score to [0, 1]
            hallucination_score = min(hallucination_score, 1.0)

            result = {
                "hallucination_score": hallucination_score,
                "indicators": hallucination_indicators,
                "is_hallucination": hallucination_score > 0.5,
                "confidence": "low" if hallucination_score > 0.5 else "high",
            }

            logger.info(
                f"🔍 Hallucination score: {hallucination_score:.3f} ({len(hallucination_indicators)} indicators)"
            )
            return result

        except Exception as e:
            logger.warning(f"⚠️  Hallucination detection failed: {e}")
            return {
                "hallucination_score": 0.5,
                "indicators": [],
                "is_hallucination": False,
                "confidence": "medium",
                "error": str(e),
            }

    def evaluate_answer_quality(
        self,
        question: str,
        answer: str,
        context: str,
        context_sources: Optional[List[Dict]] = None,
        reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive quality evaluation combining all metrics

        Args:
            question: Original question
            answer: Generated answer
            context: Context text
            context_sources: Optional list of context sources
            reference: Optional reference text for factual checking

        Returns:
            Dict with comprehensive quality metrics
        """
        try:
            # Evaluate semantic similarity
            semantic_result = self.evaluate_semantic_similarity(
                answer, context, context_sources
            )

            # Evaluate factual correctness (BERTScore)
            if reference:
                factual_result = self.evaluate_bertscore(answer, reference)
            else:
                # Use context as reference
                factual_result = self.evaluate_bertscore(answer, context)

            # Detect hallucination
            hallucination_result = self.evaluate_hallucination(
                answer, context, context_sources
            )

            # Basic length and coherence checks
            length_score = self._evaluate_length(answer)
            coherence_score = self._evaluate_coherence(answer)

            # Calculate overall quality score
            # Weight: Semantic 30%, Factual 30%, Length 15%, Coherence 15%, Hallucination 10%
            overall_quality = (
                semantic_result["similarity"] * 0.30
                + factual_result["f1"] * 0.30
                + length_score * 0.15
                + coherence_score * 0.15
                + (1 - hallucination_result["hallucination_score"]) * 0.10
            )

            result = {
                "overall_quality": overall_quality,
                "semantic": semantic_result,
                "factual": factual_result,
                "hallucination": hallucination_result,
                "length": {"score": length_score},
                "coherence": {"score": coherence_score},
                "confidence": (
                    "high"
                    if overall_quality > 0.7
                    else "medium" if overall_quality > 0.5 else "low"
                ),
                "is_high_quality": overall_quality > 0.7,
            }

            logger.info(
                f"✅ Overall quality: {overall_quality:.3f} ({result['confidence']} confidence)"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Quality evaluation failed: {e}")
            return {
                "overall_quality": 0.5,
                "error": str(e),
                "confidence": "low",
                "is_high_quality": False,
            }

    def _evaluate_length(self, answer: str) -> float:
        """Evaluate answer length"""
        length = len(answer)

        if length < 50:
            return 0.3  # Too short
        elif length < 200:
            return 0.8  # Good length
        else:
            return 1.0  # Excellent length

    def _evaluate_coherence(self, answer: str) -> float:
        """Evaluate answer coherence"""
        coherence_score = 0.8  # Default good score

        # Check for coherence issues
        if "..." in answer or "???" in answer:
            coherence_score -= 0.3

        if "unknown" in answer.lower():
            coherence_score -= 0.2

        if answer.count("?") > 3:
            coherence_score -= 0.2

        # Check for sentence structure
        if not any(end in answer for end in [".", "!", "?"]):
            coherence_score -= 0.3

        return max(0.0, coherence_score)


# Singleton instance
_advanced_evaluator: Optional[AdvancedQualityEvaluator] = None


def get_advanced_evaluator() -> AdvancedQualityEvaluator:
    """Get or create the advanced quality evaluator singleton"""
    global _advanced_evaluator

    if _advanced_evaluator is None:
        _advanced_evaluator = AdvancedQualityEvaluator()

    return _advanced_evaluator
