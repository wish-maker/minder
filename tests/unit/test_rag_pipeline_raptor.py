"""Unit tests for rag-pipeline/domain/raptor.py (#487).

RAPTOR's clustering (agglomerative_clusters) and tree-build orchestration
(build_tree) are pure control flow around injected `summarize_fn`/`embed_fn`
callables, so they're tested with fakes — no real Ollama/numpy-heavy ML
dependency needed beyond numpy itself (already a real, present dependency,
unlike scikit-learn/scipy which this module deliberately avoids — see
docs/architecture/raptor-rag.md).

Loaded by-path (hyphenated service dir); pyproject sets asyncio_mode=auto, so
the async tests need no decorator.
"""

import importlib.util
import threading
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "domain"
    / "raptor.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_raptor", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


raptor = _load()


def _synthetic_two_groups(dim: int = 6, per_group: int = 6):
    """Two obviously-distinct embedding clusters (near two orthogonal unit
    vectors), deterministic (no randomness) so clustering assertions never flake."""
    group_a = [[1.0] + [0.0] * (dim - 1) for _ in range(per_group)]
    group_b = [[0.0, 1.0] + [0.0] * (dim - 2) for _ in range(per_group)]
    return group_a + group_b


# --- agglomerative_clusters ---------------------------------------------------


def test_clusters_empty_input():
    assert raptor.agglomerative_clusters([]) == []


def test_clusters_single_embedding():
    assert raptor.agglomerative_clusters([[1.0, 0.0]]) == [[0]]


def test_clusters_separates_distinct_groups():
    embeddings = _synthetic_two_groups()
    clusters = raptor.agglomerative_clusters(embeddings, target_cluster_size=5)
    # 12 embeddings / target_cluster_size=5 -> target_k=round(2.4)=2
    assert len(clusters) == 2
    # Each returned cluster is pure — every member belongs to the same original
    # group (indices 0-5 = group A, 6-11 = group B), never mixed.
    for cluster in clusters:
        groups = {0 if i < 6 else 1 for i in cluster}
        assert len(groups) == 1


def test_clusters_identical_embeddings_collapse_together():
    embeddings = [[1.0, 0.0, 0.0]] * 5
    clusters = raptor.agglomerative_clusters(embeddings, target_cluster_size=5)
    assert len(clusters) == 1
    assert sorted(clusters[0]) == [0, 1, 2, 3, 4]


# --- build_tree ----------------------------------------------------------------


async def _summarize_ok(text: str) -> str:
    return f"summary({len(text)} chars)"


async def _embed_ok(texts):
    # Deterministic fake: same input text -> same fake vector.
    return [[float(len(t) % 7), 0.0] for t in texts]


async def test_build_tree_empty_below_two_chunks():
    # A single chunk can't be clustered at all — build_tree's own while-loop
    # condition (len(current_texts) > 1) makes this a natural no-op, not a
    # special case the caller needs to guard against.
    nodes = await raptor.build_tree(
        ["leaf-0"], ["only chunk"], [[1.0, 0.0]], _summarize_ok, _embed_ok
    )
    assert nodes == []


async def test_build_tree_creates_level_1_referencing_real_leaf_ids():
    leaf_ids = [f"leaf-{i}" for i in range(12)]
    leaf_texts = [f"chunk {i}" for i in range(12)]
    embeddings = _synthetic_two_groups()

    nodes = await raptor.build_tree(
        leaf_ids, leaf_texts, embeddings, _summarize_ok, _embed_ok, max_levels=1
    )

    level_1 = [n for n in nodes if n["level"] == 1]
    assert len(level_1) == 2  # two obviously-distinct groups -> two summaries
    assert all(n["level"] == 1 for n in nodes)  # max_levels=1 respected
    all_children = {cid for n in level_1 for cid in n["children_ids"]}
    assert all_children == set(leaf_ids)  # every leaf accounted for, real IDs
    assert len({n["id"] for n in nodes}) == len(nodes)  # unique node IDs


async def test_build_tree_collapses_to_a_single_root_without_a_level_cap():
    leaf_ids = [f"leaf-{i}" for i in range(12)]
    leaf_texts = [f"chunk {i}" for i in range(12)]
    embeddings = _synthetic_two_groups()

    nodes = await raptor.build_tree(
        leaf_ids, leaf_texts, embeddings, _summarize_ok, _embed_ok, max_levels=5
    )

    levels = sorted({n["level"] for n in nodes})
    assert levels == [1, 2]  # 12 -> 2 (level 1) -> 1 (level 2, the root)
    root = [n for n in nodes if n["level"] == 2]
    assert len(root) == 1
    level_1_ids = {n["id"] for n in nodes if n["level"] == 1}
    assert (
        set(root[0]["children_ids"]) == level_1_ids
    )  # root's children are the level-1 nodes


async def test_build_tree_degrades_to_truncated_text_on_summarize_failure():
    async def summarize_fails(text: str) -> str:
        raise RuntimeError("llm down")

    leaf_ids = ["a", "b"]
    leaf_texts = ["x" * 800, "y" * 800]
    nodes = await raptor.build_tree(
        leaf_ids, leaf_texts, [[1.0, 0.0], [0.0, 1.0]], summarize_fails, _embed_ok
    )

    assert len(nodes) == 1
    # Degraded to a truncated concat of the cluster's own text, not empty/dropped.
    assert nodes[0]["text"].startswith("x" * 100) or nodes[0]["text"].startswith(
        "y" * 100
    )
    assert len(nodes[0]["text"]) <= 500


async def test_build_tree_degrades_to_truncated_text_on_empty_summary():
    async def summarize_empty(text: str) -> str:
        return ""

    nodes = await raptor.build_tree(
        ["a", "b"],
        ["hello world " * 50, "goodbye world " * 50],
        [[1.0, 0.0], [0.0, 1.0]],
        summarize_empty,
        _embed_ok,
    )
    assert len(nodes) == 1
    assert nodes[0]["text"]  # non-empty, fell back to truncated concat


async def test_build_tree_propagates_embedding_failure():
    async def embed_fails(texts):
        raise RuntimeError("embedding backend down")

    with pytest.raises(RuntimeError, match="embedding backend down"):
        await raptor.build_tree(
            ["a", "b"],
            ["one", "two"],
            [[1.0, 0.0], [0.0, 1.0]],
            _summarize_ok,
            embed_fails,
        )


async def test_build_tree_runs_clustering_off_the_event_loop():
    """agglomerative_clusters is synchronous, O(k^2)-per-merge CPU work -- it
    must run via asyncio.to_thread so building a tree for one document can't
    stall every other in-flight request on the service (matching the same
    convention already used for every other blocking call in this codebase)."""
    main_thread_id = threading.get_ident()
    seen_thread_ids = []

    orig_clusters = raptor.agglomerative_clusters

    def spy_clusters(*args, **kwargs):
        seen_thread_ids.append(threading.get_ident())
        return orig_clusters(*args, **kwargs)

    raptor.agglomerative_clusters = spy_clusters
    try:
        await raptor.build_tree(
            [f"leaf-{i}" for i in range(12)],
            [f"chunk {i}" for i in range(12)],
            _synthetic_two_groups(),
            _summarize_ok,
            _embed_ok,
            max_levels=1,
        )
    finally:
        raptor.agglomerative_clusters = orig_clusters

    assert seen_thread_ids  # clustering actually ran
    assert all(tid != main_thread_id for tid in seen_thread_ids)
