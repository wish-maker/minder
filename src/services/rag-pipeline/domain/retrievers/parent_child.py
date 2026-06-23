"""
Parent-Child Retriever

Implements hierarchical retrieval where small child chunks are used
for precise search, but parent context is returned for better understanding.

This provides both precision (small chunks) and context (parent chunks).
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ParentChildRetriever:
    """
    Parent-child retriever for hierarchical document chunks

    Retrieves results using child chunks for precision, but returns
    parent context for better understanding. This approach provides:
    - Precise matching (small chunks)
    - Better context (parent chunks)
    - Reduced loss of information

    Attributes:
        hierarchies (Dict): Hierarchy data per knowledge base
        child_index (Dict): Child chunks per knowledge base

    Example:
        >>> retriever = ParentChildRetriever()
        >>> retriever.index_hierarchy("kb_123", hierarchy_data)
        >>> results = retriever.retrieve_with_parent_context("kb_123", child_results)
    """

    def __init__(self):
        """Initialize parent-child retriever"""
        self.hierarchies: Dict[str, List[Dict]] = {}
        self.child_index: Dict[str, List[Dict]] = {}

        logger.info("✅ ParentChildRetriever initialized")

    def index_hierarchy(self, kb_id: str, hierarchy: List[Dict[str, Any]]) -> None:
        """
        Index parent-child hierarchy for knowledge base

        Args:
            kb_id: Knowledge base identifier
            hierarchy: List hierarchy structure with nodes

        Raises:
            ValueError: If kb_id empty or hierarchy invalid
        """
        if not kb_id:
            raise ValueError("kb_id cannot be empty")

        if not hierarchy:
            raise ValueError("hierarchy cannot be empty")

        try:
            # Store full hierarchy
            self.hierarchies[kb_id] = hierarchy

            # Index child chunks for search
            self.child_index[kb_id] = [
                item for item in hierarchy if item.get("type") == "child"
            ]

            logger.info(
                f"✅ Indexed hierarchy for KB {kb_id}: "
                f"{len(self.child_index[kb_id])} children, "
                f"{len(hierarchy)} total nodes"
            )

        except Exception as e:
            logger.error(f"Failed to index hierarchy for KB {kb_id}: {e}")
            raise

    def retrieve_with_parent_context(
        self, kb_id: str, child_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve child results enhanced with parent context

        Args:
            kb_id: Knowledge base identifier
            child_results: List of child chunk results

        Returns:
            Enhanced results with parent context where appropriate

        Raises:
            ValueError: If kb_id empty
        """
        if not kb_id:
            raise ValueError("kb_id cannot be empty")

        if not child_results:
            logger.warning("No child results to enhance")
            return []

        if kb_id not in self.hierarchies:
            logger.warning(
                f"⚠️ No hierarchy found for KB {kb_id}, returning child results as-is"
            )
            return child_results

        enhanced_results = []
        parent_ids_seen = set()

        for child_result in child_results:
            child_id = child_result.get("id", "")

            if not child_id:
                # Invalid child result, keep as-is
                enhanced_results.append(child_result)
                continue

            # Find parent for this child
            parent_entry = self._find_parent(kb_id, child_id)

            if parent_entry and parent_entry["id"] not in parent_ids_seen:
                # Return parent context for first child from each parent
                enhanced_results.append(
                    {
                        "text": parent_entry.get("text", ""),
                        "source": child_result.get("source", ""),
                        "score": child_result.get("score", 0.0),
                        "context_type": "parent",
                        "parent_id": parent_entry["id"],
                        "child_id": child_id,
                    }
                )
                parent_ids_seen.add(parent_entry["id"])
            else:
                # No parent found or already seen, return child as-is
                enhanced_results.append(child_result)

        logger.debug(
            f"Enhanced {len(child_results)} results with parent context "
            f"({len(parent_ids_seen)} unique parents returned)"
        )
        return enhanced_results

    def _find_parent(self, kb_id: str, child_id: str) -> Dict[str, Any]:
        """
        Find parent node for a given child ID

        Args:
            kb_id: Knowledge base identifier
            child_id: Child node ID

        Returns:
            Parent node dict or None if not found
        """
        if kb_id not in self.hierarchies:
            return None

        hierarchy = self.hierarchies[kb_id]

        # Search for parent
        for item in hierarchy:
            if item.get("type") == "parent" and child_id in item.get("children", []):
                return item

            # Recursive search in nested structures
            if "children" in item:
                for child in item["children"]:
                    if child.get("type") == "parent" and child_id in child.get(
                        "children", []
                    ):
                        return child
                    if "children" in child:
                        for grandchild in child["children"]:
                            if grandchild.get(
                                "type"
                            ) == "parent" and child_id in grandchild.get(
                                "children", []
                            ):
                                return grandchild
            elif "clusters" in item:
                for cluster in item["clusters"]:
                    for node in cluster:
                        if node.get("type") == "parent" and child_id in node.get(
                            "children", []
                        ):
                            return node

        return None
