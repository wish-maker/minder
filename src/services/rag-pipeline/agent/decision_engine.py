"""
Agent Decision Engine for Agentic RAG

LLM-driven dynamic RAG pipeline selection and optimization.
Analyzes query characteristics and selects optimal RAG techniques.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class QueryComplexity(Enum):
    """Query complexity levels"""
    SIMPLE = "simple"           # Direct factual query
    MODERATE = "moderate"       # Requires some reasoning
    COMPLEX = "complex"         # Multi-hop reasoning needed
    AMBIGUOUS = "ambiguous"     # Clarification needed


class RetrievalStrategy(Enum):
    """Available retrieval strategies"""
    BASIC = "basic"                    # Simple vector search
    HYBRID = "hybrid"                  # Vector + keyword search
    HIERARCHICAL = "hierarchical"      # Multi-level retrieval
    DECOMPOSITION = "decomposition"    # Query decomposition


@dataclass
class QueryAnalysis:
    """Query analysis results"""
    original_query: str
    complexity: QueryComplexity
    keywords: List[str]
    entities: List[str]
    intent: str
    requires_external: bool = False
    confidence: float = 0.0


@dataclass
class PipelineDecision:
    """RAG pipeline configuration decision"""
    retrieval_strategy: RetrievalStrategy
    top_k: int
    similarity_threshold: float
    use_reranking: bool
    use_query_expansion: bool
    use_hyde: bool
    use_self_rag: bool
    chunking_strategy: str
    reasoning_required: bool


class AgentDecisionEngine:
    """
    LLM-powered decision engine for dynamic RAG pipeline optimization

    Analyzes queries and selects optimal RAG techniques based on:
    - Query complexity and structure
    - Information density requirements
    - Reasoning depth needed
    - Performance constraints
    """

    def __init__(self, ollama_host: str = "minder-ollama:11434"):
        self.ollama_host = ollama_host
        self.decision_history: List[Dict] = []

    async def analyze_query(self, query: str) -> QueryAnalysis:
        """
        Analyze query using LLM to determine characteristics

        Returns comprehensive analysis for pipeline decision making
        """
        analysis_prompt = f"""Analyze this query for RAG optimization:

Query: "{query}"

Provide JSON response:
{{
    "complexity": "simple|moderate|complex|ambiguous",
    "keywords": ["keyword1", "keyword2"],
    "entities": ["entity1", "entity2"],
    "intent": "factual|analytical|comparative|explanatory",
    "requires_external": true/false,
    "confidence": 0.0-1.0
}}
"""

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"http://{self.ollama_host}/api/generate",
                    json={
                        "model": "llama3.2",
                        "prompt": analysis_prompt,
                        "stream": False,
                        "format": "json"
                    }
                )
                response.raise_for_status()
                result = response.json()

                # Parse LLM response
                analysis_data = json.loads(result.get("response", "{}"))

                return QueryAnalysis(
                    original_query=query,
                    complexity=QueryComplexity(analysis_data.get("complexity", "moderate")),
                    keywords=analysis_data.get("keywords", []),
                    entities=analysis_data.get("entities", []),
                    intent=analysis_data.get("intent", "factual"),
                    requires_external=analysis_data.get("requires_external", False),
                    confidence=analysis_data.get("confidence", 0.5)
                )

        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}, using fallback")
            return self._fallback_analysis(query)

    def _fallback_analysis(self, query: str) -> QueryAnalysis:
        """Fallback rule-based analysis when LLM unavailable"""
        words = query.lower().split()
        keywords = [w for w in words if len(w) > 4]

        # Simple complexity estimation
        if len(words) < 5:
            complexity = QueryComplexity.SIMPLE
        elif len(words) < 10:
            complexity = QueryComplexity.MODERATE
        else:
            complexity = QueryComplexity.COMPLEX

        return QueryAnalysis(
            original_query=query,
            complexity=complexity,
            keywords=keywords,
            entities=[],
            intent="factual",
            requires_external=False,
            confidence=0.6
        )

    async def decide_pipeline(self, analysis: QueryAnalysis) -> PipelineDecision:
        """
        Decide optimal RAG pipeline configuration based on query analysis

        Uses LLM to make sophisticated decisions about:
        - Which retrieval strategy to use
        - How many documents to retrieve
        - Whether to use advanced techniques (HyDE, Self-RAG, etc.)
        """
        decision_prompt = f"""Based on this query analysis, select optimal RAG pipeline:

Query Analysis:
- Original: "{analysis.original_query}"
- Complexity: {analysis.complexity.value}
- Keywords: {', '.join(analysis.keywords)}
- Entities: {', '.join(analysis.entities)}
- Intent: {analysis.intent}
- Requires External: {analysis.requires_external}
- Confidence: {analysis.confidence}

Select pipeline configuration (JSON):
{{
    "retrieval_strategy": "basic|hybrid|hierarchical|decomposition",
    "top_k": 5-20,
    "similarity_threshold": 0.5-0.9,
    "use_reranking": true/false,
    "use_query_expansion": true/false,
    "use_hyde": true/false,
    "use_self_rag": true/false,
    "chunking_strategy": "fixed|semantic|recursive",
    "reasoning_required": true/false
}}

Rules:
- Simple queries: basic strategy, lower top_k
- Complex queries: hybrid/decomposition, reranking, query expansion
- Ambiguous: HyDE for query enhancement
- Low confidence: Self-RAG for reflection
"""

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"http://{self.ollama_host}/api/generate",
                    json={
                        "model": "llama3.2",
                        "prompt": decision_prompt,
                        "stream": False,
                        "format": "json"
                    }
                )
                response.raise_for_status()
                result = response.json()

                # Parse LLM decision
                decision_data = json.loads(result.get("response", "{}"))

                decision = PipelineDecision(
                    retrieval_strategy=RetrievalStrategy(decision_data.get("retrieval_strategy", "hybrid")),
                    top_k=decision_data.get("top_k", 10),
                    similarity_threshold=decision_data.get("similarity_threshold", 0.7),
                    use_reranking=decision_data.get("use_reranking", True),
                    use_query_expansion=decision_data.get("use_query_expansion", False),
                    use_hyde=decision_data.get("use_hyde", False),
                    use_self_rag=decision_data.get("use_self_rag", False),
                    chunking_strategy=decision_data.get("chunking_strategy", "semantic"),
                    reasoning_required=decision_data.get("reasoning_required", False)
                )

                # Record decision for learning
                self.decision_history.append({
                    "query": analysis.original_query,
                    "analysis": analysis.__dict__,
                    "decision": decision.__dict__
                })

                logger.info(f"Agent decision: {decision.retrieval_strategy.value} strategy with top_k={decision.top_k}")
                return decision

        except Exception as e:
            logger.warning(f"LLM decision failed: {e}, using heuristic")
            return self._heuristic_decision(analysis)

    def _heuristic_decision(self, analysis: QueryAnalysis) -> PipelineDecision:
        """Fallback heuristic-based decision making"""

        # Base configuration
        decision = PipelineDecision(
            retrieval_strategy=RetrievalStrategy.HYBRID,
            top_k=10,
            similarity_threshold=0.7,
            use_reranking=True,
            use_query_expansion=False,
            use_hyde=False,
            use_self_rag=False,
            chunking_strategy="semantic",
            reasoning_required=False
        )

        # Adjust based on complexity
        if analysis.complexity == QueryComplexity.SIMPLE:
            decision.retrieval_strategy = RetrievalStrategy.BASIC
            decision.top_k = 5
            decision.use_reranking = False

        elif analysis.complexity == QueryComplexity.COMPLEX:
            decision.retrieval_strategy = RetrievalStrategy.HIERARCHICAL
            decision.top_k = 15
            decision.use_query_expansion = True
            decision.reasoning_required = True

        elif analysis.complexity == QueryComplexity.AMBIGUOUS:
            decision.use_hyde = True
            decision.top_k = 12

        # Low confidence -> use Self-RAG for reflection
        if analysis.confidence < 0.5:
            decision.use_self_rag = True
            decision.top_k += 5

        return decision

    async def optimize_pipeline(self, current_decision: PipelineDecision,
                               performance_metrics: Dict[str, float]) -> PipelineDecision:
        """
        Optimize pipeline based on performance feedback

        Uses reinforcement learning principles to improve decisions
        """
        # Extract key metrics
        retrieval_latency = performance_metrics.get("retrieval_latency", 0.0)
        answer_relevance = performance_metrics.get("answer_relevance", 0.0)

        optimized = PipelineDecision(
            retrieval_strategy=current_decision.retrieval_strategy,
            top_k=current_decision.top_k,
            similarity_threshold=current_decision.similarity_threshold,
            use_reranking=current_decision.use_reranking,
            use_query_expansion=current_decision.use_query_expansion,
            use_hyde=current_decision.use_hyde,
            use_self_rag=current_decision.use_self_rag,
            chunking_strategy=current_decision.chunking_strategy,
            reasoning_required=current_decision.reasoning_required
        )

        # Adjust based on performance
        if retrieval_latency > 2.0 and answer_relevance > 0.8:
            # Fast enough, high quality -> can reduce top_k
            optimized.top_k = max(5, current_decision.top_k - 2)

        elif answer_relevance < 0.6:
            # Low quality -> increase retrieval and enable advanced features
            optimized.top_k = min(20, current_decision.top_k + 3)
            optimized.use_reranking = True
            if not optimized.use_query_expansion:
                optimized.use_query_expansion = True

        logger.info(f"Pipeline optimized: top_k {current_decision.top_k} -> {optimized.top_k}")
        return optimized

    def get_decision_stats(self) -> Dict[str, Any]:
        """Get statistics about decision patterns"""
        if not self.decision_history:
            return {"total_decisions": 0}

        strategy_counts = {}
        complexity_counts = {}

        for record in self.decision_history:
            strategy = record["decision"]["retrieval_strategy"]
            complexity = record["analysis"]["complexity"]

            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
            complexity_counts[complexity] = complexity_counts.get(complexity, 0) + 1

        return {
            "total_decisions": len(self.decision_history),
            "strategy_distribution": strategy_counts,
            "complexity_distribution": complexity_counts,
            "avg_confidence": sum(r["analysis"]["confidence"] for r in self.decision_history) / len(self.decision_history)
        }
