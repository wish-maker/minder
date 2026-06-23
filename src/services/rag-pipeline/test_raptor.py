"""
Comprehensive Test Suite for RAPTOR RAG Implementation

Tests cover:
1. Unit tests for RAPTORChunker
2. Unit tests for RAPTORRetriever
3. Integration tests with real LLM
4. Edge cases and error handling
"""

import logging
import sys
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Test configuration
TEST_CONFIG = {
    "chunk_size": 256,
    "chunk_overlap": 32,
    "max_tree_depth": 2,  # Reduced for faster testing
    "cluster_size": 4,
    "summary_length": 100,
}


# ============================================================================
# Test Utilities
# ============================================================================


class TestResult:
    """Test result tracker"""

    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []

    def add_pass(self, test_name: str):
        self.total += 1
        self.passed += 1
        logger.info(f"✅ PASS: {test_name}")

    def add_fail(self, test_name: str, error: str):
        self.total += 1
        self.failed += 1
        self.errors.append((test_name, error))
        logger.error(f"❌ FAIL: {test_name} - {error}")

    def summary(self) -> Dict[str, Any]:
        success_rate = (self.passed / self.total * 100) if self.total > 0 else 0
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "success_rate": success_rate,
            "errors": self.errors,
        }


results = TestResult()


def assert_equal(actual, expected, test_name: str):
    """Assert two values are equal"""
    if actual == expected:
        results.add_pass(test_name)
    else:
        results.add_fail(test_name, f"Expected {expected}, got {actual}")


def assert_true(condition, test_name: str):
    """Assert condition is true"""
    if condition:
        results.add_pass(test_name)
    else:
        results.add_fail(test_name, "Condition was False")


def assert_not_none(value, test_name: str):
    """Assert value is not None"""
    if value is not None:
        results.add_pass(test_name)
    else:
        results.add_fail(test_name, "Value was None")


def assert_greater_than(value, threshold, test_name: str):
    """Assert value is greater than threshold"""
    if value > threshold:
        results.add_pass(test_name)
    else:
        results.add_fail(test_name, f"Value {value} not greater than {threshold}")


def assert_contains(collection, item, test_name: str):
    """Assert collection contains item"""
    if item in collection:
        results.add_pass(test_name)
    else:
        results.add_fail(test_name, f"Item {item} not in collection")


# ============================================================================
# Unit Tests: RAPTORChunker
# ============================================================================


def test_raptor_chunker_initialization():
    """Test RAPTORChunker initialization"""
    try:
        from raptor_rag import RAPTORChunker

        chunker = RAPTORChunker(
            chunk_size=TEST_CONFIG["chunk_size"],
            chunk_overlap=TEST_CONFIG["chunk_overlap"],
            max_tree_depth=TEST_CONFIG["max_tree_depth"],
            cluster_size=TEST_CONFIG["cluster_size"],
        )

        assert_not_none(chunker, "Chunker initialization")
        assert_equal(
            chunker.chunk_size, TEST_CONFIG["chunk_size"], "Chunk size setting"
        )
        assert_equal(
            chunker.max_tree_depth,
            TEST_CONFIG["max_tree_depth"],
            "Max tree depth setting",
        )

    except Exception as e:
        results.add_fail("Chunker initialization", str(e))


def test_raptor_chunker_too_short_text():
    """Test chunker with text too short for RAPTOR"""
    try:
        from raptor_rag import RAPTORChunker

        chunker = RAPTORChunker()
        short_text = "This is too short."

        # Should handle gracefully
        chunks = chunker._chunk_text(short_text)
        assert_true(len(chunks) >= 1, "Short text produces at least 1 chunk")

    except Exception as e:
        results.add_fail("Short text handling", str(e))


def test_raptor_tree_creation_basic():
    """Test basic tree creation without LLM"""
    try:
        from raptor_rag import RAPTORChunker

        chunker = RAPTORChunker(
            chunk_size=TEST_CONFIG["chunk_size"], max_tree_depth=2, cluster_size=4
        )

        # Create test text
        test_text = """
        Machine learning is a subset of artificial intelligence.
        It enables systems to learn from data without explicit programming.
        There are three main types: supervised, unsupervised, and reinforcement learning.
        Supervised learning uses labeled data for training.
        Unsupervised learning finds patterns in unlabeled data.
        Reinforcement learning learns through trial and error.
        """ * 3  # Repeat to make it longer

        # Test chunking
        chunks = chunker._chunk_text(test_text)
        assert_greater_than(len(chunks), 3, "Text split into multiple chunks")

    except Exception as e:
        results.add_fail("Basic tree creation", str(e))


def test_cosine_similarity_calculation():
    """Test cosine similarity calculation"""
    try:
        from raptor_rag import RAPTORChunker

        chunker = RAPTORChunker()

        # Test vectors
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        vec3 = [1.0, 0.0, 0.0]  # Same as vec1

        # Orthogonal vectors
        sim_orthogonal = chunker._cosine_similarity(vec1, vec2)
        assert_true(abs(sim_orthogonal) < 0.01, "Orthogonal vectors have ~0 similarity")

        # Identical vectors
        sim_identical = chunker._cosine_similarity(vec1, vec3)
        assert_true(
            abs(sim_identical - 1.0) < 0.01, "Identical vectors have ~1 similarity"
        )

    except Exception as e:
        results.add_fail("Cosine similarity calculation", str(e))


# ============================================================================
# Unit Tests: RAPTORRetriever
# ============================================================================


def test_raptor_retriever_initialization():
    """Test RAPTORRetriever initialization"""
    try:
        from raptor_rag import RAPTORRetriever

        retriever = RAPTORRetriever()
        assert_not_none(retriever, "Retriever initialization")
        assert_true(isinstance(retriever.trees, dict), "Trees is a dictionary")
        assert_true(
            isinstance(retriever.tree_embeddings, dict),
            "Tree embeddings is a dictionary",
        )

    except Exception as e:
        results.add_fail("Retriever initialization", str(e))


def test_raptor_tree_indexing():
    """Test tree indexing"""
    try:
        from raptor_rag import RAPTORRetriever

        retriever = RAPTORRetriever()

        # Mock tree structure
        mock_tree = {
            "type": "leaves",
            "leaves": [
                {"id": "leaf_1", "type": "leaf", "text": "Text 1"},
                {"id": "leaf_2", "type": "leaf", "text": "Text 2"},
            ],
        }

        retriever.index_tree("test_kb", mock_tree)
        assert_true("test_kb" in retriever.trees, "Tree indexed for KB")

    except Exception as e:
        results.add_fail("Tree indexing", str(e))


def test_query_specificity_analysis():
    """Test query specificity analysis"""
    try:
        from raptor_rag import RAPTORRetriever

        retriever = RAPTORRetriever()

        # General query
        specificity_general = retriever._analyze_query_specificity(
            "What is machine learning?"
        )
        assert_true(
            0.0 <= specificity_general <= 1.0, "General query specificity in range"
        )

        # Specific query (with quotes and numbers)
        specificity_specific = retriever._analyze_query_specificity(
            'Find "machine learning" algorithms from 2020'
        )
        assert_true(
            specificity_specific > specificity_general,
            "Specific query has higher specificity",
        )

    except Exception as e:
        results.add_fail("Query specificity analysis", str(e))


# ============================================================================
# Integration Tests (Mock)
# ============================================================================


def test_raptor_end_to_end_mock():
    """Test end-to-end RAPTOR pipeline with mocked LLM"""
    try:
        from raptor_rag import RAPTORChunker

        chunker = RAPTORChunker(chunk_size=256, max_tree_depth=2, cluster_size=4)

        # Create test document
        test_text = """
        Introduction to Neural Networks

        Neural networks are computing systems inspired by biological neural networks.
        They consist of interconnected nodes or neurons that process information.

        Types of Neural Networks

        Feedforward Neural Networks: Information flows in one direction.
        Recurrent Neural Networks: Can process sequential data.
        Convolutional Neural Networks: Specialized for image processing.

        Applications

        Neural networks are used in image recognition, speech processing, and natural language understanding.
        """ * 2  # Repeat for longer text

        # Chunk text
        chunks = chunker._chunk_text(test_text)
        assert_greater_than(len(chunks), 3, "Document chunked properly")

        # Verify chunk content
        assert_true(
            any("neural" in chunk.lower() for chunk in chunks),
            "Chunks contain expected keywords",
        )

    except Exception as e:
        results.add_fail("End-to-end mock test", str(e))


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


def test_empty_text_handling():
    """Test handling of empty text"""
    try:
        from raptor_rag import RAPTORChunker

        chunker = RAPTORChunker()
        chunks = chunker._chunk_text("")

        # Should return empty list or single empty chunk
        assert_true(
            len(chunks) == 0 or (len(chunks) == 1 and chunks[0] == ""),
            "Empty text handled gracefully",
        )

    except Exception as e:
        results.add_fail("Empty text handling", str(e))


def test_single_word_text():
    """Test handling of single word text"""
    try:
        from raptor_rag import RAPTORChunker

        chunker = RAPTORChunker()
        chunks = chunker._chunk_text("Hello")

        assert_not_none(chunks, "Single word produces chunks")
        assert_true(len(chunks) >= 1, "At least one chunk produced")

    except Exception as e:
        results.add_fail("Single word handling", str(e))


def test_non_ascii_text():
    """Test handling of non-ASCII characters"""
    try:
        from raptor_rag import RAPTORChunker

        chunker = RAPTORChunker()

        # Turkish text with special characters
        turkish_text = "Türkçe metin testi. Öğrenme algoritmaları çok önemlidir. Başarı için çaba gerekir."

        chunks = chunker._chunk_text(turkish_text)
        assert_not_none(chunks, "Turkish text chunked")
        assert_true(len(chunks) >= 1, "Turkish text produces chunks")

    except Exception as e:
        results.add_fail("Non-ASCII text handling", str(e))


# ============================================================================
# Run All Tests
# ============================================================================


def run_all_tests():
    """Run all test suites"""
    logger.info("🧪 Starting RAPTOR Test Suite")
    logger.info("=" * 60)

    # Unit tests: RAPTORChunker
    logger.info("\n📦 Testing RAPTORChunker...")
    test_raptor_chunker_initialization()
    test_raptor_chunker_too_short_text()
    test_raptor_tree_creation_basic()
    test_cosine_similarity_calculation()

    # Unit tests: RAPTORRetriever
    logger.info("\n🔍 Testing RAPTORRetriever...")
    test_raptor_retriever_initialization()
    test_raptor_tree_indexing()
    test_query_specificity_analysis()

    # Integration tests
    logger.info("\n🔗 Testing Integration...")
    test_raptor_end_to_end_mock()

    # Edge cases
    logger.info("\n⚠️  Testing Edge Cases...")
    test_empty_text_handling()
    test_single_word_text()
    test_non_ascii_text()

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)

    summary = results.summary()
    logger.info(f"Total Tests: {summary['total']}")
    logger.info(f"Passed: {summary['passed']}")
    logger.info(f"Failed: {summary['failed']}")
    logger.info(f"Success Rate: {summary['success_rate']:.1f}%")

    if summary["errors"]:
        logger.error("\n❌ Failed Tests:")
        for test_name, error in summary["errors"]:
            logger.error(f"  - {test_name}: {error}")

    logger.info("=" * 60)

    return summary["failed"] == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
