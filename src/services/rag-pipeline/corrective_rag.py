"""
Corrective RAG (CRAG) Implementation for Raspberry Pi 4
Web search fallback when retrieval quality is poor
"""

import logging
import os
from typing import Any, Dict, List
import httpx

logger = logging.getLogger(__name__)


class CorrectiveRetriever:
    """
    Corrective RAG with web search fallback

    When retrieval quality is poor, fallback to web search to fill knowledge gaps
    """

    def __init__(self):
        """Initialize CRAG components"""
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        self.serper_api_key = os.getenv("SERPER_API_KEY", "")
        self.quality_threshold = 0.5  # Threshold for triggering fallback
        self.max_web_results = 5  # Max web search results to retrieve

        # Check if web search is available
        self.web_search_available = bool(self.tavily_api_key or self.serper_api_key)

    def evaluate_retrieval_quality(
        self, results: List[Dict], query: str
    ) -> Dict[str, Any]:
        """
        Evaluate quality of retrieval results

        Args:
            results: Retrieved documents with scores
            query: Original query string

        Returns:
            Quality assessment with metrics
        """
        if not results:
            return {
                "quality": "poor",
                "average_score": 0.0,
                "result_count": 0,
                "should_fallback": True,
                "reason": "No results retrieved",
            }

        # Calculate average score
        scores = [r.get("score", 0.0) for r in results]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Check score distribution
        high_quality_count = sum(1 for s in scores if s > 0.7)
        low_quality_count = sum(1 for s in scores if s < 0.3)

        # Determine quality
        quality = "good" if avg_score >= self.quality_threshold else "poor"

        # Should fallback if quality is poor
        should_fallback = (
            quality == "poor"
            or avg_score < self.quality_threshold
            or low_quality_count > len(results) / 2
        )

        return {
            "quality": quality,
            "average_score": avg_score,
            "result_count": len(results),
            "high_quality_count": high_quality_count,
            "low_quality_count": low_quality_count,
            "should_fallback": should_fallback,
            "reason": f"Average score {avg_score:.3f} below threshold {self.quality_threshold}",
        }

    async def search_web_tavily(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Search web using Tavily API

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of web search results
        """
        if not self.tavily_api_key:
            logger.warning("⚠️ Tavily API key not configured")
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = "https://api.tavily.com/search"
                params = {
                    "api_key": self.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",  # RPi optimization: basic search
                    "include_answer": True,
                    "include_raw_content": False,
                    "include_images": False,
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()

                # Parse results
                results = []
                if data.get("answer"):
                    results.append(
                        {
                            "title": "Generated Answer",
                            "text": data["answer"],
                            "url": "",
                            "score": 0.9,  # High score for generated answer
                            "source": "tavily_answer",
                        }
                    )

                for result in data.get("results", []):
                    results.append(
                        {
                            "title": result.get("title", ""),
                            "text": result.get("content", "")[
                                :500
                            ],  # Limit content length
                            "url": result.get("url", ""),
                            "score": 0.7,  # Moderate score for web results
                            "source": "tavily_search",
                        }
                    )

                logger.info(f"🌐 Tavily search returned {len(results)} results")
                return results[:max_results]

        except Exception as e:
            logger.warning(f"⚠️ Tavily search failed: {e}")
            return []

    async def search_web_serper(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Search web using SerperAPI (Google Search API)

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of web search results
        """
        if not self.serper_api_key:
            logger.warning("⚠️ SerperAPI key not configured")
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = "https://googleserperapi.com/search"
                params = {
                    "apiKey": self.serper_api_key,
                    "q": query,
                    "num": max_results,
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()

                # Parse results
                results = []
                for result in data.get("organic", []):
                    results.append(
                        {
                            "title": result.get("title", ""),
                            "text": result.get("snippet", "")[
                                :500
                            ],  # Limit snippet length
                            "url": result.get("link", ""),
                            "score": 0.7,  # Moderate score for web results
                            "source": "serper_search",
                        }
                    )

                logger.info(f"🌐 SerperAPI search returned {len(results)} results")
                return results[:max_results]

        except Exception as e:
            logger.warning(f"⚠️ SerperAPI search failed: {e}")
            return []

    async def retrieve_with_fallback(
        self, query: str, internal_results: List[Dict], kb_id: str, max_results: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieve with web search fallback if quality is poor

        Args:
            query: Search query
            internal_results: Results from internal knowledge base
            kb_id: Knowledge base ID
            max_results: Maximum total results to return

        Returns:
            Combined results with fallback if needed
        """
        # Evaluate internal retrieval quality
        quality_assessment = self.evaluate_retrieval_quality(internal_results, query)

        logger.info(
            f"📊 Retrieval quality assessment: {quality_assessment['quality']} "
            f"(score: {quality_assessment['average_score']:.3f})"
        )

        # If quality is good, return internal results
        if not quality_assessment["should_fallback"]:
            logger.info("✅ Internal retrieval quality sufficient, no fallback needed")
            return {
                "results": internal_results[:max_results],
                "fallback_used": False,
                "quality": quality_assessment["quality"],
                "internal_count": len(internal_results),
                "web_count": 0,
            }

        # Quality is poor, try web search fallback
        logger.warning(
            "⚠️ Internal retrieval quality poor, attempting web search fallback"
        )

        if not self.web_search_available:
            logger.warning("❌ Web search not available, returning internal results")
            return {
                "results": internal_results[:max_results],
                "fallback_used": False,
                "quality": quality_assessment["quality"],
                "internal_count": len(internal_results),
                "web_count": 0,
                "reason": "Web search API not configured",
            }

        # Try web search
        web_results = []
        try:
            # Prefer Tavily, fallback to SerperAPI
            if self.tavily_api_key:
                web_results = await self.search_web_tavily(query, self.max_web_results)
            elif self.serper_api_key:
                web_results = await self.search_web_serper(query, self.max_web_results)
            else:
                logger.warning("❌ No web search API configured")
                return {
                    "results": internal_results[:max_results],
                    "fallback_used": False,
                    "quality": quality_assessment["quality"],
                    "internal_count": len(internal_results),
                    "web_count": 0,
                    "reason": "No web search API configured",
                }
        except Exception as e:
            logger.warning(f"⚠️ Web search failed: {e}")
            return {
                "results": internal_results[:max_results],
                "fallback_used": False,
                "quality": quality_assessment["quality"],
                "internal_count": len(internal_results),
                "web_count": 0,
                "reason": f"Web search error: {e}",
            }

        if not web_results:
            logger.warning("⚠️ Web search returned no results")
            return {
                "results": internal_results[:max_results],
                "fallback_used": False,
                "quality": quality_assessment["quality"],
                "internal_count": len(internal_results),
                "web_count": 0,
                "reason": "Web search returned no results",
            }

        # Combine internal and web results
        # Give web results a slight score boost to prioritize them
        combined_results = []

        # Add web results first (with boost)
        for web_result in web_results:
            web_result["score"] = (
                web_result.get("score", 0.7) * 1.2
            )  # 20% boost for web results
            combined_results.append(web_result)

        # Add internal results
        for internal_result in internal_results:
            combined_results.append(internal_result)

        # Sort by score and limit
        combined_results = sorted(
            combined_results, key=lambda x: x["score"], reverse=True
        )
        final_results = combined_results[:max_results]

        logger.info(
            f"✅ CRAG fallback successful: {len(web_results)} web results + "
            f"{len(internal_results)} internal results = {len(final_results)} final results"
        )

        return {
            "results": final_results,
            "fallback_used": True,
            "quality": "improved",
            "internal_count": len(internal_results),
            "web_count": len(web_results),
            "final_count": len(final_results),
            "reason": "Web search fallback applied successfully",
        }


# Global CRAG retriever
crag_retriever = CorrectiveRetriever()
