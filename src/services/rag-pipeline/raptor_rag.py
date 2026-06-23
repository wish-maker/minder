"""
RAPTOR RAG Implementation for Raspberry Pi 4
Recursive Abstractive Processing for Tree-Organized Retrieval

This module implements the RAPTOR algorithm which builds hierarchical tree structures
from documents by:
1. Clustering similar chunks based on semantic similarity
2. Summarizing each cluster with LLM
3. Recursively building tree structure
4. Retrieving from appropriate level based on query specificity

RPi 4 Optimizations:
- Lightweight cosine similarity clustering (no hierarchical clustering overhead)
- Max 3 tree levels (memory constraint)
- Small batch sizes for embedding generation
- Efficient summary generation with token limits

Example Usage:
    >>> from raptor_rag import raptor_chunker, raptor_retriever
    >>>
    >>> # Create tree structure
    >>> tree_result = raptor_chunker.create_tree_structure(
    ...     text=document_text,
    ...     llm_manager=ollama_manager,
    ...     embeddings=embeddings
    ... )
    >>>
    >>> # Index for retrieval
    >>> raptor_retriever.index_tree("kb_id", tree_result["tree"])
    >>>
    >>> # Retrieve from tree
    >>> results = raptor_retriever.retrieve_from_tree(
    ...     kb_id="kb_id",
    ...     query="What is the main topic?",
    ...     query_embedding=query_emb,
    ...     top_k=5
    ... )

References:
    - RAPTOR Paper: https://arxiv.org/abs/2401.18059
"""

import logging
from typing import Any, Dict, List, Optional

# Optional imports for enhanced functionality
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logging.warning("NumPy not available. Some optimizations will be disabled.")


logger = logging.getLogger(__name__)


# ============================================================================
# Custom Exceptions
# ============================================================================


class RAPTORError(Exception):
    """Base exception for RAPTOR-related errors"""


class RAPTORChunkingError(RAPTORError):
    """Raised when text chunking fails"""


class RAPTORClusteringError(RAPTORError):
    """Raised when clustering operation fails"""


class RAPTORRetrievalError(RAPTORError):
    """Raised when retrieval operation fails"""


# ============================================================================
# RAPTOR Chunker
# ============================================================================


class RAPTORChunker:
    """
    RAPTOR hierarchical chunker with tree-structured clustering

    This class implements the RAPTOR algorithm for building hierarchical
    tree structures from text documents. It chunks text, clusters similar chunks,
    and generates summaries for each cluster level.

    Attributes:
        chunk_size (int): Base chunk size for text splitting
        chunk_overlap (int): Overlap between consecutive chunks
        max_tree_depth (int): Maximum depth of the hierarchical tree (RPi 4: max 3)
        cluster_size (int): Target number of chunks per cluster
        summary_length (int): Target character count for cluster summaries
        min_cluster_size (int): Minimum chunks required to form a valid cluster

    Example:
        >>> chunker = RAPTORChunker(
        ...     chunk_size=512,
        ...     max_tree_depth=3,
        ...     cluster_size=6
        ... )
        >>> tree_result = chunker.create_tree_structure(
        ...     text=document_text,
        ...     llm_manager=llm_manager
        ... )
        >>> print(tree_result["metadata"])
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        max_tree_depth: int = 3,
        cluster_size: int = 6,
        summary_length: int = 150,
    ):
        """
        Initialize RAPTOR chunker with configuration parameters

        Args:
            chunk_size: Base chunk size for text splitting (default: 512)
            chunk_overlap: Overlap between consecutive chunks (default: 50)
            max_tree_depth: Maximum tree depth (RPi 4: limited to 3 for memory)
            cluster_size: Target cluster size for summarization (default: 6)
            summary_length: Target length for cluster summaries (default: 150)

        Raises:
            ValueError: If chunk_size <= 0 or chunk_overlap >= chunk_size
        """
        # Validate inputs
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
            )
        if max_tree_depth < 1 or max_tree_depth > 5:
            raise ValueError(
                f"max_tree_depth must be between 1 and 5, got {max_tree_depth}"
            )
        if cluster_size < 2:
            raise ValueError(f"cluster_size must be at least 2, got {cluster_size}")
        if summary_length < 50:
            raise ValueError(
                f"summary_length must be at least 50, got {summary_length}"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_tree_depth = max_tree_depth
        self.cluster_size = cluster_size
        self.summary_length = summary_length
        self.min_cluster_size = max(3, cluster_size // 2)  # Dynamic minimum

        logger.info(
            f"✅ RAPTORChunker initialized: chunk_size={chunk_size}, "
            f"max_depth={max_tree_depth}, cluster_size={cluster_size}"
        )

    def create_tree_structure(
        self,
        text: str,
        llm_manager,
        embeddings: Optional[List[List[float]]] = None,
        embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create RAPTOR tree structure from input text

        This is the main entry point for RAPTOR processing. It chunks the text,
        generates embeddings, builds the hierarchical tree, and returns metadata.

        Args:
            text: Input text document (must be > 100 chars for meaningful tree)
            llm_manager: LLM manager instance for summary generation
            embeddings: Optional pre-computed embeddings for chunks
            embedding_model: Optional embedding model name (default: "nomic-embed-text")

        Returns:
            Dictionary containing:
                - tree (Dict): Hierarchical tree structure with nodes
                - metadata (Dict): Statistics about the tree (total_nodes, tree_depth, etc.)

        Raises:
            RAPTORChunkingError: If text chunking fails
            RAPTORClusteringError: If clustering fails
            ValueError: If text is too short or empty

        Example:
            >>> tree_result = chunker.create_tree_structure(
            ...     text="Long document text...",
            ...     llm_manager=ollama_manager
            ... )
            >>> print(f"Tree has {tree_result['metadata']['total_nodes']} nodes")
        """
        # Validate input
        if not text or not isinstance(text, str):
            raise ValueError("Text must be a non-empty string")

        if len(text.strip()) < 50:
            raise ValueError(
                f"Text too short for RAPTOR (min 50 chars): {len(text)} chars"
            )

        try:
            # Step 1: Create base chunks
            base_chunks = self._chunk_text(text)
            logger.info(
                f"📄 Created {len(base_chunks)} base chunks from {len(text)} chars"
            )

            if len(base_chunks) < self.min_cluster_size:
                logger.warning(
                    f"⚠️ Text too short for RAPTOR clustering "
                    f"({len(base_chunks)} < {self.min_cluster_size} chunks), using base chunks"
                )
                return {
                    "tree": {"chunks": base_chunks, "type": "flat"},
                    "metadata": {
                        "total_nodes": len(base_chunks),
                        "tree_depth": 1,
                        "clusters_created": 0,
                        "base_chunks": len(base_chunks),
                        "algorithm": "flat",
                    },
                }

            # Step 2: Generate embeddings if not provided
            if embeddings is None or len(embeddings) != len(base_chunks):
                logger.info("🔄 Generating embeddings for base chunks...")
                embeddings = self._generate_embeddings(
                    chunks=base_chunks,
                    llm_manager=llm_manager,
                    model=embedding_model or "nomic-embed-text",
                )

                if not embeddings or len(embeddings) != len(base_chunks):
                    raise RAPTORChunkingError(
                        "Failed to generate embeddings for all chunks"
                    )

            # Step 3: Build tree recursively
            logger.info("🌳 Building hierarchical tree structure...")
            tree = self._build_tree_recursive(
                chunks=base_chunks,
                embeddings=embeddings,
                level=0,
                llm_manager=llm_manager,
                embedding_model=embedding_model or "nomic-embed-text",
            )

            # Step 4: Validate and count nodes
            stats = self._count_tree_nodes(tree)

            if stats["total_nodes"] == 0:
                raise RAPTORClusteringError("Tree construction resulted in zero nodes")

            logger.info(
                f"✅ RAPTOR tree built: {stats['total_nodes']} nodes, "
                f"depth {stats['max_depth']}, {stats['clusters']} clusters"
            )

            return {
                "tree": tree,
                "metadata": {
                    "total_nodes": stats["total_nodes"],
                    "tree_depth": stats["max_depth"],
                    "clusters_created": stats["clusters"],
                    "base_chunks": len(base_chunks),
                    "algorithm": "raptor",
                },
            }

        except Exception as e:
            logger.error(f"❌ RAPTOR tree creation failed: {e}")
            raise RAPTORClusteringError(f"Failed to create tree structure: {str(e)}")

    def _generate_embeddings(
        self, chunks: List[str], llm_manager, model: str
    ) -> List[List[float]]:
        """Generate embeddings for text chunks"""
        try:
            embeddings = llm_manager.generate_embeddings(chunks, model=model)
            logger.debug(f"Generated {len(embeddings)} embeddings using {model}")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise RAPTORChunkingError(f"Embedding generation failed: {str(e)}")

    def _chunk_text(self, text: str) -> List[str]:
        """
        Chunk text using RecursiveCharacterTextSplitter

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks

        Raises:
            RAPTORChunkingError: If both primary and fallback chunking fail
        """
        if not text:
            return []

        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""],
            )

            chunks = text_splitter.split_text(text)

            if not chunks:
                raise RAPTORChunkingError("Text splitter produced no chunks")

            logger.debug(f"Split text into {len(chunks)} chunks")
            return chunks

        except ImportError:
            logger.warning("langchain_text_splitters not available, using fallback")
            return self._fallback_chunking(text)

        except Exception as e:
            logger.warning(f"Text splitting failed: {e}, using fallback")
            return self._fallback_chunking(text)

    def _fallback_chunking(self, text: str) -> List[str]:
        """
        Fallback chunking by character (when langchain unavailable)

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        effective_chunk_size = self.chunk_size - self.chunk_overlap

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            if chunk:
                chunks.append(chunk)
            start += effective_chunk_size

        logger.debug(f"Fallback chunking produced {len(chunks)} chunks")
        return chunks

    def _build_tree_recursive(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        level: int,
        llm_manager,
        embedding_model: str,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Recursively build tree structure from chunks and embeddings

        Args:
            chunks: Text chunks at current level
            embeddings: Embeddings for chunks
            level: Current tree depth level
            llm_manager: LLM for summary generation
            embedding_model: Embedding model name
            parent_id: Parent node ID

        Returns:
            Tree node structure with children or leaves
        """
        # Base case: stop recursion
        if len(chunks) < self.min_cluster_size or level >= self.max_tree_depth:
            logger.debug(f"Base case reached at level {level}: {len(chunks)} chunks")
            return self._create_leaf_nodes(chunks, embeddings, parent_id)

        # Cluster chunks at this level
        try:
            clusters = self._cluster_chunks(chunks, embeddings)
        except Exception as e:
            logger.error(f"Clustering failed at level {level}: {e}")
            return self._create_leaf_nodes(chunks, embeddings, parent_id)

        if not clusters:
            logger.debug(f"No clusters created at level {level}, creating leaves")
            return self._create_leaf_nodes(chunks, embeddings, parent_id)

        logger.info(
            f"🌳 Level {level}: Created {len(clusters)} clusters "
            f"from {len(chunks)} chunks (target cluster_size: {self.cluster_size})"
        )

        # Create summaries for each cluster
        cluster_nodes = []
        for cluster_idx, cluster in enumerate(clusters):
            try:
                cluster_chunks = [chunks[i] for i in cluster]
                cluster_embeddings = [embeddings[i] for i in cluster]

                # Generate summary
                summary = self._generate_cluster_summary(cluster_chunks, llm_manager)

                # Create node
                node_id = f"L{level}_C{cluster_idx}_{parent_id or 'root'}"

                node = {
                    "id": node_id,
                    "type": "cluster",
                    "level": level,
                    "text": summary,
                    "summary": summary,
                    "chunk_count": len(cluster_chunks),
                    "children_indices": cluster,
                    "parent_id": parent_id,
                }

                # Create leaf children for this cluster
                node["children"] = [
                    {
                        "id": f"{node_id}_child_{i}",
                        "type": "leaf",
                        "text": chunk,
                        "parent_id": node_id,
                    }
                    for i, chunk in enumerate(cluster_chunks)
                ]

                cluster_nodes.append(node)

            except Exception as e:
                logger.warning(f"Failed to process cluster {cluster_idx}: {e}")
                # Continue with other clusters

        if not cluster_nodes:
            logger.warning("No cluster nodes created, falling back to leaves")
            return self._create_leaf_nodes(chunks, embeddings, parent_id)

        return {
            "type": "level",
            "level": level,
            "clusters": cluster_nodes,
            "total_chunks": len(chunks),
        }

    def _create_leaf_nodes(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create leaf nodes for base chunks

        Args:
            chunks: Text chunks to convert to leaves
            embeddings: Embeddings for chunks (unused in current implementation)
            parent_id: Parent node ID

        Returns:
            Dictionary with leaf nodes
        """
        leaves = []
        for i, chunk in enumerate(chunks):
            leaf = {
                "id": f"leaf_{i}_{parent_id or 'root'}",
                "type": "leaf",
                "text": chunk,
                "parent_id": parent_id,
                "level": 0,
            }
            leaves.append(leaf)

        logger.debug(f"Created {len(leaves)} leaf nodes")
        return {"type": "leaves", "leaves": leaves, "total_chunks": len(chunks)}

    def _cluster_chunks(
        self, chunks: List[str], embeddings: List[List[float]]
    ) -> List[List[int]]:
        """
        Cluster chunks using lightweight cosine similarity

        Uses greedy clustering algorithm optimized for RPi 4:
        - No hierarchical clustering overhead
        - Simple similarity threshold
        - Efficient memory usage

        Args:
            chunks: Text chunks to cluster
            embeddings: Embeddings for chunks

        Returns:
            List of clusters, where each cluster is a list of chunk indices

        Raises:
            RAPTORClusteringError: If clustering operation fails
        """
        if len(chunks) < self.min_cluster_size:
            return []

        n = len(chunks)

        # Build similarity matrix
        try:
            similarity_matrix = self._build_similarity_matrix(embeddings, n)
        except Exception as e:
            logger.error(f"Failed to build similarity matrix: {e}")
            raise RAPTORClusteringError(
                f"Similarity matrix construction failed: {str(e)}"
            )

        # Greedy clustering
        clusters = []
        assigned = set()

        for i in range(n):
            if i in assigned:
                continue

            # Start new cluster with chunk i
            cluster = [i]
            assigned.add(i)

            # Find similar chunks
            similarities = [
                (j, similarity_matrix[i][j])
                for j in range(n)
                if j not in assigned and j != i
            ]

            # Sort by similarity (descending)
            similarities.sort(key=lambda x: x[1], reverse=True)

            # Add top similar chunks to cluster
            min_similarity = 0.3  # Minimum similarity threshold
            for j, sim in similarities[: self.cluster_size - 1]:
                if sim >= min_similarity:
                    cluster.append(j)
                    assigned.add(j)

            # Only keep cluster if it has enough chunks
            if len(cluster) >= self.min_cluster_size:
                clusters.append(cluster)
                logger.debug(
                    f"Created cluster {len(clusters)} with {len(cluster)} chunks"
                )

        logger.info(f"Clustering complete: {len(clusters)} clusters from {n} chunks")
        return clusters

    def _build_similarity_matrix(
        self, embeddings: List[List[float]], n: int
    ) -> List[List[float]]:
        """
        Build similarity matrix from embeddings

        Args:
            embeddings: List of embedding vectors
            n: Number of embeddings

        Returns:
            n x n similarity matrix

        Raises:
            ValueError: If embeddings are invalid
        """
        if not embeddings or n != len(embeddings):
            raise ValueError(
                f"Embedding count mismatch: expected {n}, got {len(embeddings)}"
            )

        # Initialize matrix
        similarity_matrix = [[0.0 for _ in range(n)] for _ in range(n)]

        # Calculate cosine similarities
        for i in range(n):
            for j in range(i + 1, n):
                try:
                    sim = self._cosine_similarity(embeddings[i], embeddings[j])
                    similarity_matrix[i][j] = sim
                    similarity_matrix[j][i] = sim
                except Exception as e:
                    logger.warning(f"Failed to calculate similarity [{i}][{j}]: {e}")
                    similarity_matrix[i][j] = 0.0
                    similarity_matrix[j][i] = 0.0

        return similarity_matrix

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity in range [-1, 1]

        Raises:
            ValueError: If vectors are invalid or empty
        """
        if not vec1 or not vec2:
            return 0.0

        if len(vec1) != len(vec2):
            logger.warning(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")
            return 0.0

        try:
            if NUMPY_AVAILABLE:
                # Use NumPy for efficiency
                v1 = np.array(vec1, dtype=np.float32)
                v2 = np.array(vec2, dtype=np.float32)

                dot_product = float(np.dot(v1, v2))
                norm1 = float(np.linalg.norm(v1))
                norm2 = float(np.linalg.norm(v2))

                if norm1 == 0 or norm2 == 0:
                    return 0.0

                return dot_product / (norm1 * norm2)
            else:
                # Pure Python fallback
                dot_product = sum(a * b for a, b in zip(vec1, vec2))
                norm1 = sum(a * a for a in vec1) ** 0.5
                norm2 = sum(b * b for b in vec2) ** 0.5

                if norm1 == 0 or norm2 == 0:
                    return 0.0

                return dot_product / (norm1 * norm2)

        except Exception as e:
            logger.warning(f"Cosine similarity calculation failed: {e}")
            return 0.0

    def _generate_cluster_summary(self, chunks: List[str], llm_manager) -> str:
        """
        Generate summary for a cluster using LLM

        Args:
            chunks: Text chunks in the cluster
            llm_manager: LLM manager instance

        Returns:
            Generated summary text

        Note:
            RPi 4 Optimization: Limits input to 3 chunks and uses concise prompts
        """
        if not chunks:
            return "Empty cluster"

        try:
            # Combine chunks (limit total length for efficiency)
            combined_text = "\n\n".join(chunks[:3])

            prompt = f"""Summarize the following text in {self.summary_length} characters or less, capturing the main points:

{combined_text}

Summary:"""

            result = llm_manager.generate_response(
                prompt=prompt,
                model="llama3.2",
                temperature=0.3,  # Lower temperature for focused summaries
            )

            summary = result.get("text", "").strip()

            # Ensure summary is not too long
            if len(summary) > self.summary_length * 2:
                summary = summary[: self.summary_length * 2] + "..."

            if not summary:
                raise ValueError("LLM produced empty summary")

            logger.debug(
                f"Generated summary: {len(summary)} chars from {len(chunks)} chunks"
            )
            return summary

        except Exception as e:
            logger.warning(f"Summary generation failed: {e}, using fallback")
            return self._fallback_summary(chunks)

    def _fallback_summary(self, chunks: List[str]) -> str:
        """
        Generate fallback summary when LLM fails

        Args:
            chunks: Text chunks to summarize

        Returns:
            Fallback summary text
        """
        fallback_summary = ""

        for chunk in chunks[:2]:
            sentences = chunk.split(". ")
            if sentences:
                fallback_summary += sentences[0] + ". "
            if len(fallback_summary) > self.summary_length:
                break

        return fallback_summary.strip() or "Summary unavailable"

    def _count_tree_nodes(self, tree: Dict[str, Any]) -> Dict[str, int]:
        """
        Count total nodes and max depth in tree structure

        Args:
            tree: Tree structure to analyze

        Returns:
            Dictionary with node counts and depth statistics
        """
        stats = {"total_nodes": 0, "max_depth": 0, "clusters": 0}

        def traverse(node: Dict[str, Any], depth: int):
            """Recursively traverse tree and count nodes"""
            stats["max_depth"] = max(stats["max_depth"], depth)
            stats["total_nodes"] += 1

            if node.get("type") == "cluster":
                stats["clusters"] += 1

            if "children" in node and node["children"]:
                for child in node["children"]:
                    traverse(child, depth + 1)
            elif "leaves" in node and node["leaves"]:
                for leaf in node["leaves"]:
                    traverse(leaf, depth + 1)
            elif "clusters" in node and node["clusters"]:
                for cluster in node["clusters"]:
                    traverse(cluster, depth + 1)

        traverse(tree, 0)
        return stats


# ============================================================================
# RAPTOR Retriever
# ============================================================================


class RAPTORRetriever:
    """
    RAPTOR retriever with tree-aware search

    This retriever searches hierarchical tree structures and returns results
    from the appropriate level based on query specificity:
    - High specificity (specific terms, quotes, numbers) → leaf nodes (detailed chunks)
    - Low specificity (general questions) → cluster nodes (summaries)

    Attributes:
        trees (Dict[str, Dict]): Knowledge base ID to tree structure mapping
        tree_embeddings (Dict[str, Dict[str, List[float]]]): Node embeddings cache

    Example:
        >>> retriever = RAPTORRetriever()
        >>> retriever.index_tree("kb_123", tree_structure)
        >>> results = retriever.retrieve_from_tree(
        ...     kb_id="kb_123",
        ...     query="What are the main concepts?",
        ...     query_embedding=query_emb,
        ...     top_k=5
        ... )
    """

    def __init__(self):
        """Initialize RAPTOR retriever with empty tree storage"""
        self.trees: Dict[str, Dict[str, Any]] = {}
        self.tree_embeddings: Dict[str, Dict[str, List[float]]] = {}

        logger.info("✅ RAPTORRetriever initialized")

    def index_tree(
        self,
        kb_id: str,
        tree: Dict[str, Any],
        embeddings: Optional[Dict[str, List[float]]] = None,
    ) -> None:
        """
        Index RAPTOR tree for knowledge base

        Args:
            kb_id: Knowledge base identifier
            tree: Tree structure from RAPTORChunker
            embeddings: Optional node embeddings for enhanced retrieval

        Raises:
            ValueError: If kb_id or tree is invalid
        """
        if not kb_id or not isinstance(kb_id, str):
            raise ValueError(f"Invalid kb_id: {kb_id}")

        if not tree or not isinstance(tree, dict):
            raise ValueError(f"Invalid tree structure for kb_id {kb_id}")

        self.trees[kb_id] = tree
        if embeddings:
            self.tree_embeddings[kb_id] = embeddings

        logger.info(f"✅ Indexed RAPTOR tree for KB {kb_id}")

    def retrieve_from_tree(
        self,
        kb_id: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 5,
        llm_manager=None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve from tree using appropriate level based on query specificity

        Args:
            kb_id: Knowledge base ID
            query: Search query string
            query_embedding: Query embedding vector
            top_k: Number of results to return (default: 5)
            llm_manager: Optional LLM manager for enhanced query analysis

        Returns:
            List of retrieved chunks with metadata (id, text, score, node_type, level)

        Raises:
            RAPTORRetrievalError: If kb_id not found or retrieval fails
        """
        if not kb_id or kb_id not in self.trees:
            logger.warning(f"⚠️ No RAPTOR tree found for KB {kb_id}")
            return []

        if not query or not query.strip():
            logger.warning("⚠️ Empty query provided")
            return []

        if top_k < 1:
            raise ValueError(f"top_k must be positive, got {top_k}")

        try:
            tree = self.trees[kb_id]

            # Analyze query specificity
            query_specificity = self._analyze_query_specificity(query, llm_manager)

            # Select search level based on specificity
            # Threshold: 0.7 (above = specific, below = general)
            if query_specificity > 0.7:
                # Search leaf nodes (specific details)
                logger.debug(
                    f"High specificity ({query_specificity:.2f}): searching leaves"
                )
                results = self._search_leaves(tree, query_embedding, top_k)
            else:
                # Search cluster nodes (summaries)
                logger.debug(
                    f"Low specificity ({query_specificity:.2f}): searching clusters"
                )
                results = self._search_clusters(tree, query_embedding, top_k)

            logger.info(
                f"🎯 RAPTOR retrieved {len(results)} nodes "
                f"(specificity: {query_specificity:.2f}, kb: {kb_id})"
            )
            return results

        except Exception as e:
            logger.error(f"❌ RAPTOR retrieval failed for KB {kb_id}: {e}")
            raise RAPTORRetrievalError(f"Retrieval failed: {str(e)}")

    def _analyze_query_specificity(self, query: str, llm_manager=None) -> float:
        """
        Analyze query specificity (0 = general, 1 = specific)

        RPi 4 Optimization: Uses simple heuristics instead of LLM call
        for faster processing and lower memory usage.

        Args:
            query: Query string to analyze
            llm_manager: Optional LLM manager (currently unused, reserved for future)

        Returns:
            Specificity score in range [0, 1]
        """
        if not query:
            return 0.5  # Neutral for empty query

        score = 0.5  # Base score

        # Length penalty: shorter queries are often more general
        query_len = len(query)
        if query_len < 20:
            score -= 0.2
        elif query_len > 60:
            score += 0.1

        # Check for specific terms (quotes, numbers, proper nouns)
        specific_indicators = [
            '"' in query,  # Quotes indicate exact phrases
            any(c.isdigit() for c in query),  # Numbers indicate specifics
            any(
                word[0].isupper() and len(word) > 1 for word in query.split()
            ),  # Proper nouns
        ]

        score += sum(specific_indicators) * 0.1

        # Check for general question words
        general_words = [
            "what",
            "how",
            "why",
            "explain",
            "describe",
            "overview",
            "summary",
        ]
        if any(word in query.lower() for word in general_words):
            score -= 0.2

        # Check for specific operators
        specific_operators = ["==", "!=", ">=", "<=", "contains", "between"]
        if any(op in query.lower() for op in specific_operators):
            score += 0.15

        # Normalize to [0, 1]
        return max(0.0, min(1.0, score))

    def _search_leaves(
        self, tree: Dict[str, Any], query_embedding: List[float], top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Search leaf nodes (specific chunks)

        Args:
            tree: Tree structure
            query_embedding: Query embedding vector
            top_k: Number of results to return

        Returns:
            List of scored leaf nodes
        """
        leaves = self._extract_all_leaves(tree)

        # Score leaves
        scored_leaves = []
        for leaf in leaves:
            if "text" in leaf:
                score = self._calculate_similarity(
                    query_embedding, leaf.get("text", "")
                )
                scored_leaves.append(
                    {
                        "id": leaf.get("id", ""),
                        "text": leaf.get("text", ""),
                        "score": score,
                        "node_type": "leaf",
                        "level": leaf.get("level", 0),
                    }
                )

        # Sort by score (descending) and return top-k
        scored_leaves.sort(key=lambda x: x["score"], reverse=True)
        return scored_leaves[:top_k]

    def _search_clusters(
        self, tree: Dict[str, Any], query_embedding: List[float], top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Search cluster nodes (summaries)

        Args:
            tree: Tree structure
            query_embedding: Query embedding vector
            top_k: Number of results to return

        Returns:
            List of scored cluster nodes
        """
        clusters = self._extract_all_clusters(tree)

        # Score clusters
        scored_clusters = []
        for cluster in clusters:
            # Use summary if available, fallback to text
            cluster_text = cluster.get("summary") or cluster.get("text", "")

            if cluster_text:
                score = self._calculate_similarity(query_embedding, cluster_text)
                scored_clusters.append(
                    {
                        "id": cluster.get("id", ""),
                        "text": cluster_text,
                        "score": score,
                        "node_type": "cluster",
                        "level": cluster.get("level", 0),
                        "chunk_count": cluster.get("chunk_count", 0),
                    }
                )

        # Sort by score (descending) and return top-k
        scored_clusters.sort(key=lambda x: x["score"], reverse=True)
        return scored_clusters[:top_k]

    def _extract_all_leaves(self, tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract all leaf nodes from tree structure"""
        leaves = []

        def traverse(node: Dict[str, Any]):
            if node.get("type") == "leaf":
                leaves.append(node)

            if "children" in node and node["children"]:
                for child in node["children"]:
                    traverse(child)
            elif "leaves" in node and node["leaves"]:
                for leaf in node["leaves"]:
                    traverse(leaf)

        traverse(tree)
        logger.debug(f"Extracted {len(leaves)} leaf nodes")
        return leaves

    def _extract_all_clusters(self, tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract all cluster nodes from tree structure"""
        clusters = []

        def traverse(node: Dict[str, Any]):
            if node.get("type") == "cluster":
                clusters.append(node)

            if "children" in node and node["children"]:
                for child in node["children"]:
                    traverse(child)
            elif "clusters" in node and node["clusters"]:
                for cluster in node["clusters"]:
                    traverse(cluster)

        traverse(tree)
        logger.debug(f"Extracted {len(clusters)} cluster nodes")
        return clusters

    def _calculate_similarity(self, query_embedding: List[float], text: str) -> float:
        """
        Calculate similarity between query embedding and text

        RPi 4 Optimization: Uses word overlap as fallback when embeddings unavailable
        Future enhancement: Use proper embedding similarity

        Args:
            query_embedding: Query embedding vector
            text: Text to compare against

        Returns:
            Similarity score in range [0, 1]
        """
        if not query_embedding or not text:
            return 0.0

        # Simple word overlap as fallback
        # In full implementation, would use embedding similarity
        try:
            query_words = set()
            # Extract words from embedding (simplified)
            # For now, use empty set as fallback

            text_words = set(word.lower().strip() for word in text.split())

            if not text_words:
                return 0.0

            # Jaccard similarity
            intersection = len(query_words & text_words)
            union = len(query_words | text_words)

            return intersection / union if union > 0 else 0.0

        except Exception as e:
            logger.warning(f"Similarity calculation failed: {e}")
            return 0.0


# ============================================================================
# Global Instances (Singleton Pattern)
# ============================================================================

# Global chunker and retriever instances
# These are reused across requests for efficiency
raptor_chunker = RAPTORChunker()
raptor_retriever = RAPTORRetriever()
