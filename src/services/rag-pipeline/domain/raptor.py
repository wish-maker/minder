"""
RAPTOR tree construction (#487)

Recursive clustering + LLM summarization over a document's chunk embeddings,
building the tree of abstraction levels RAPTOR retrieval searches across.
See docs/architecture/raptor-rag.md for the design decisions (why plain
numpy agglomerative clustering instead of GMM/scikit-learn, why per-document
scope, why the tree lands in the same Qdrant collection as everything else).

This is a domain component: no Qdrant/FastAPI/state imports. `summarize_fn`/
`embed_fn` are injected async callables (same "explicit deps in" convention
as rag/methods/*.py and domain/expansion/hyde.py) so this module has zero
knowledge of Ollama, HTTP, or the app's global state, and is trivially
testable with fakes.
"""

import logging
import uuid
from typing import Awaitable, Callable, Dict, List, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# A document needs at least this many chunks before a tree is worth building —
# below this there's nothing meaningful to cluster (docs/architecture/raptor-rag.md #1).
MIN_CHUNKS_FOR_TREE = 6

# Above this, skip tree-building rather than pay O(k²) clustering on a huge upload.
MAX_CHUNKS_FOR_TREE = 300

# Each clustering pass aims to shrink the node count by roughly this factor.
TARGET_CLUSTER_SIZE = 5

# Levels 1..N beyond the leaves (level 0). A level that fails to shrink the node
# count stops the loop early regardless of this cap.
MAX_TREE_LEVELS = 3


def _cosine_distance_matrix(vectors: np.ndarray) -> np.ndarray:
    """Pairwise cosine distance (1 - cosine similarity), diagonal set to +inf so
    a node is never picked as its own nearest neighbour."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1e-12  # guard a stray all-zero embedding, not a real vector
    normalized = vectors / norms
    similarity = normalized @ normalized.T
    distance = 1.0 - similarity
    np.fill_diagonal(distance, np.inf)
    return distance


def agglomerative_clusters(
    embeddings: Sequence[Sequence[float]],
    target_cluster_size: int = TARGET_CLUSTER_SIZE,
) -> List[List[int]]:
    """Bottom-up average-linkage agglomerative clustering by cosine distance.

    Starts with every embedding as its own singleton cluster and repeatedly
    merges the two closest clusters (average distance between their members)
    until the cluster count shrinks to roughly `len(embeddings) /
    target_cluster_size` (at least 1). Returns each cluster as a list of
    indices into `embeddings`. O(k^2) per merge, O(n) merges — fine at the
    per-document scale (tens to a couple hundred chunks) this is used at;
    not intended for corpus-wide clustering.
    """
    n = len(embeddings)
    if n <= 1:
        return [[i] for i in range(n)]

    vectors = np.array(embeddings, dtype=float)
    distance = _cosine_distance_matrix(vectors)
    clusters: List[List[int]] = [[i] for i in range(n)]
    target_k = max(1, round(n / target_cluster_size))

    while len(clusters) > target_k:
        best_pair = (0, 1)
        best_distance = np.inf
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                pairwise = distance[np.ix_(clusters[a], clusters[b])]
                avg = float(np.mean(pairwise))
                if avg < best_distance:
                    best_distance = avg
                    best_pair = (a, b)
        a, b = best_pair
        merged = clusters[a] + clusters[b]
        clusters = [c for i, c in enumerate(clusters) if i not in (a, b)]
        clusters.append(merged)

    return clusters


SummarizeFn = Callable[[str], Awaitable[str]]
EmbedFn = Callable[[List[str]], Awaitable[List[List[float]]]]


async def build_tree(
    leaf_ids: List[str],
    leaf_texts: List[str],
    leaf_embeddings: List[List[float]],
    summarize_fn: SummarizeFn,
    embed_fn: EmbedFn,
    max_levels: int = MAX_TREE_LEVELS,
    target_cluster_size: int = TARGET_CLUSTER_SIZE,
) -> List[Dict]:
    """Recursively cluster + summarize leaf chunks into a RAPTOR tree.

    `leaf_ids` are the Qdrant point IDs already assigned to the leaf chunks
    (level 0) — used to populate `children_ids` on the level-1 summaries, so
    every returned node is immediately ready to become a Qdrant PointStruct
    with no further ID-resolution step needed by the caller.

    Returns a flat list of new nodes (levels 1..N, never level 0):
    ``{"id": str, "level": int, "text": str, "embedding": [...], "children_ids": [...]}``.
    Stops early if a level fails to shrink the node count (nothing further to
    gain) or `max_levels` is reached. Never raises on a failed/empty summary —
    degrades to a truncated concatenation of the cluster's own text instead of
    dropping the cluster, matching `OllamaManager.generate_response`'s own
    never-raise contract for the same failure (a down LLM backend degrades
    that one cluster's "summary," it doesn't abort the whole tree). `embed_fn`
    is NOT wrapped the same way — an embedding-backend failure propagates, since
    a partially-embedded level can't be turned into valid Qdrant points at all.
    """
    nodes: List[Dict] = []
    current_ids = list(leaf_ids)
    current_texts = list(leaf_texts)
    current_embeddings = list(leaf_embeddings)

    level = 1
    while level <= max_levels and len(current_texts) > 1:
        clusters = agglomerative_clusters(current_embeddings, target_cluster_size)
        if len(clusters) >= len(current_texts):
            break  # clustering didn't reduce anything further — nothing to gain

        new_ids: List[str] = []
        new_texts: List[str] = []
        new_children: List[List[str]] = []
        for indices in clusters:
            combined = "\n\n".join(current_texts[i] for i in indices)
            try:
                summary = await summarize_fn(combined)
            except Exception as e:  # noqa: BLE001 — degrade, don't abort the tree
                logger.warning(f"RAPTOR cluster summarization failed: {e}")
                summary = ""
            if not summary:
                summary = combined[:500]
            new_ids.append(str(uuid.uuid4()))
            new_texts.append(summary)
            new_children.append([current_ids[i] for i in indices])

        new_embeddings = await embed_fn(new_texts)
        for node_id, text, embedding, children in zip(
            new_ids, new_texts, new_embeddings, new_children
        ):
            nodes.append(
                {
                    "id": node_id,
                    "level": level,
                    "text": text,
                    "embedding": embedding,
                    "children_ids": children,
                }
            )

        current_ids, current_texts, current_embeddings = (
            new_ids,
            new_texts,
            new_embeddings,
        )
        level += 1

    return nodes
