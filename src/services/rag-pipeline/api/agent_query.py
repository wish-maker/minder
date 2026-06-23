"""
Agent-based Query API Endpoint

Intelligent RAG query processing with LLM-driven pipeline optimization.
Replaces static query processing with adaptive agent decision making.
"""

import logging
from typing import Any, Dict, Optional

from agent.decision_engine import AgentDecisionEngine, PipelineDecision, QueryAnalysis
from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentQueryRequest(BaseModel):
    """Agent-powered query request"""

    query: str
    knowledge_base_id: Optional[str] = None
    enable_optimization: bool = True
    user_preferences: Optional[Dict[str, Any]] = None


class AgentQueryResponse(BaseModel):
    """Agent-powered query response"""

    query: str
    answer: str
    sources: list
    pipeline_config: Dict[str, Any]
    query_analysis: Dict[str, Any]
    performance_metrics: Dict[str, float]
    reasoning: Optional[str] = None


class AgentQueryService:
    """
    Service for intelligent RAG query processing

    Uses Agent Decision Engine to:
    1. Analyze query characteristics
    2. Select optimal RAG pipeline
    3. Execute retrieval with adaptive configuration
    4. Provide performance feedback
    """

    def __init__(self):
        self.decision_engine = AgentDecisionEngine()
        # Integration with existing RAG services will be added here

    async def process_agent_query(
        self, request: AgentQueryRequest
    ) -> AgentQueryResponse:
        """
        Process query with intelligent pipeline selection

        Args:
            request: Query with agent optimization enabled

        Returns:
            Response with answer, pipeline config, and analysis
        """
        try:
            # Phase 1: Query Analysis
            logger.info(f"Agent analysis for query: {request.query}")
            query_analysis = await self.decision_engine.analyze_query(request.query)

            # Phase 2: Pipeline Decision
            pipeline_decision = await self.decision_engine.decide_pipeline(
                query_analysis
            )

            # Phase 3: Execute with Optimized Pipeline
            answer, sources, metrics = await self._execute_optimized_pipeline(
                request.query, pipeline_decision, request.knowledge_base_id
            )

            # Phase 4: Performance Feedback (if optimization enabled)
            if request.enable_optimization:
                optimized_decision = await self.decision_engine.optimize_pipeline(
                    pipeline_decision, metrics
                )
                pipeline_decision = optimized_decision

            return AgentQueryResponse(
                query=request.query,
                answer=answer,
                sources=sources,
                pipeline_config=self._serialize_decision(pipeline_decision),
                query_analysis=self._serialize_analysis(query_analysis),
                performance_metrics=metrics,
            )

        except Exception as e:
            logger.error(f"Agent query processing failed: {e}")
            raise HTTPException(status_code=500, detail=f"Agent query failed: {str(e)}")

    async def _execute_optimized_pipeline(
        self, query: str, decision: PipelineDecision, knowledge_base_id: Optional[str]
    ) -> tuple:
        """
        Execute RAG pipeline with agent-selected configuration

        This integrates with existing RAG services:
        - Knowledge base service
        - Retrieval service
        - Advanced techniques (HyDE, Self-RAG, etc.)
        """
        # Placeholder for integration with existing services
        # Will be implemented in next step

        # Simulated response for now
        answer = f"Agent-optimized answer for: {query}"
        sources = [{"doc_id": "1", "content": "Sample source", "score": 0.85}]
        metrics = {
            "retrieval_latency": 0.5,
            "answer_relevance": 0.85,
            "total_time": 0.8,
        }

        return answer, sources, metrics

    def _serialize_decision(self, decision: PipelineDecision) -> Dict[str, Any]:
        """Convert PipelineDecision to dict"""
        return {
            "retrieval_strategy": decision.retrieval_strategy.value,
            "top_k": decision.top_k,
            "similarity_threshold": decision.similarity_threshold,
            "use_reranking": decision.use_reranking,
            "use_query_expansion": decision.use_query_expansion,
            "use_hyde": decision.use_hyde,
            "use_self_rag": decision.use_self_rag,
            "chunking_strategy": decision.chunking_strategy,
            "reasoning_required": decision.reasoning_required,
        }

    def _serialize_analysis(self, analysis: QueryAnalysis) -> Dict[str, Any]:
        """Convert QueryAnalysis to dict"""
        return {
            "complexity": analysis.complexity.value,
            "keywords": analysis.keywords,
            "entities": analysis.entities,
            "intent": analysis.intent,
            "requires_external": analysis.requires_external,
            "confidence": analysis.confidence,
        }


# Global service instance
agent_query_service = AgentQueryService()
