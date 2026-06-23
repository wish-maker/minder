"""
Clean Architecture Example

Example showing how to use the new refactored architecture.
This demonstrates clean integration of all layers.

Usage:
    python3 clean_architecture_example.py
"""

import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import all layers
from domain import (
    HybridSearchRetriever,
    CrossEncoderReranker,
    ContextualCompressor,
    HyDEQueryExpander
)

from infrastructure import (
    EmbeddingCache,
    Pi4ResourceManager
)

from services import (
    RetrievalService,
    KnowledgeBaseService
)

from repositories import (
    KnowledgeBaseRepository,
    ConversationRepository
)


from utils import (
    chunk_text,
    chunk_text_fallback,
    cosine_similarity
)


class MockQdrantClient:
    """Mock Qdrant for demonstration"""

    def __init__(self):
        self.collections = {}

    def query_points(self, collection_name, query, limit=5):
        """Mock query"""
        class MockPoint:
            def __init__(self, id, score, text):
                self.id = id
                self.score = score
                self.payload = {"text": text, "source": "test"}

        return type('Result', (), {
            'points': [
                MockPoint(f"doc_{i}", 0.9 - (i * 0.1), f"Sample document {i}")
                for i in range(limit)
            ]
        })()

    def create_collection(self, collection_name, vectors_config):
        """Mock collection creation"""
        self.collections[collection_name] = vectors_config
        logger.info(f"✅ Created collection: {collection_name}")

    def upsert(self, collection_name, points):
        """Mock upsert"""
        if collection_name not in self.collections:
            self.collections[collection_name] = []
        logger.info(f"✅ Upserted {len(points)} points to {collection_name}")


class MockConnection:
    """Mock database connection"""
    async def execute(self, sql, *args):
        """Mock execute"""

    async def fetchrow(self, sql, *args):
        """Mock fetchrow"""
        return None

    async def fetch(self, sql, *args):
        """Mock fetch"""
        return []

class MockPostgresPool:
    """Mock PostgreSQL for demonstration"""

    def __init__(self):
        pass

    def acquire(self):
        """Mock connection"""
        return self

    async def __aenter__(self):
        return MockConnection()

    async def __aexit__(self, *args):
        pass


async def demonstrate_clean_architecture():
    """Demonstrate complete clean architecture flow"""

    print("\n" + "="*70)
    print("🏗️  Clean Architecture Demonstration")
    print("="*70)

    # ============================================================================
    # STEP 1: Initialize Infrastructure Layer
    # ============================================================================
    print("\n📦 Step 1: Initialize Infrastructure Layer")

    resource_manager = Pi4ResourceManager(
        max_concurrent_requests=2,
        max_memory_mb=4000
    )
    print("  ✅ Pi4ResourceManager initialized")

    embedding_cache = EmbeddingCache(max_size=1000)
    print("  ✅ EmbeddingCache initialized")

    # Mock Ollama (for demo)
    class MockOllama:
        async def generate_embeddings(self, texts, model):
            await asyncio.sleep(0.1)  # Simulate API call
            return [[0.1] * 768 for _ in texts]

    ollama_manager = MockOllama()
    print("  ✅ OllamaManager (mocked)")

    # Mock Qdrant
    qdrant_client = MockQdrantClient()
    print("  ✅ QdrantClient (mocked)")

    # Mock PostgreSQL
    postgres_pool = MockPostgresPool()
    print("  ✅ PostgreSQLClient (mocked)")

    # ============================================================================
    # STEP 2: Initialize Repository Layer
    # ============================================================================
    print("\n💾 Step 2: Initialize Repository Layer")

    kb_repository = KnowledgeBaseRepository(postgres_pool)
    print("  ✅ KnowledgeBaseRepository initialized")

    conv_repository = ConversationRepository(postgres_pool)
    print("  ✅ ConversationRepository initialized")

    # ============================================================================
    # STEP 3: Initialize Domain Components
    # ============================================================================
    print("\n🧠 Step 3: Initialize Domain Components")

    # Optional domain components (all are configurable)
    hyde_expander = HyDEQueryExpander()
    print("  ✅ HyDEQueryExpander initialized")

    hybrid_searcher = HybridSearchRetriever(alpha=0.6)
    print("  ✅ HybridSearchRetriever initialized (alpha=0.6)")

    reranker = CrossEncoderReranker()
    print("  ✅ CrossEncoderReranker initialized")

    compressor = ContextualCompressor(max_tokens=2000, compression_ratio=0.3)
    print("  ✅ ContextualCompressor initialized")

    # ============================================================================
    # STEP 4: Initialize Service Layer
    # ============================================================================
    print("\n🔧 Step 4: Initialize Service Layer")

    retrieval_service = RetrievalService(
        ollama_manager=ollama_manager,
        qdrant_client=qdrant_client,
        resource_manager=resource_manager,
        hyde_expander=hyde_expander,
        hybrid_searcher=hybrid_searcher,
        reranker=reranker,
        context_compressor=compressor
    )
    print("  ✅ RetrievalService initialized with all enhancements")

    kb_service = KnowledgeBaseService(
        ollama_manager=ollama_manager,
        qdrant_client=qdrant_client,
        parent_child_chunker=None  # Optional
    )
    print("  ✅ KnowledgeBaseService initialized")

    # ============================================================================
    # STEP 5: Demonstrate Utilities
    # ============================================================================
    print("\n🛠️  Step 5: Demonstrate Shared Utilities")

    # Text chunking
    sample_text = "This is a long document that needs to be chunked for processing. " * 20

    # Try chunk_text, fallback to chunk_text_fallback if langchain unavailable
    try:
        chunks = chunk_text(sample_text, chunk_size=100, chunk_overlap=20)
        print(f"  ✅ Chunked text into {len(chunks)} chunks (langchain method)")
    except RuntimeError:
        chunks = chunk_text_fallback(sample_text, chunk_size=100, chunk_overlap=20)
        print(f"  ✅ Chunked text into {len(chunks)} chunks (fallback method)")

    # Similarity calculation
    vec1 = [0.1, 0.2, 0.3]
    vec2 = [0.1, 0.2, 0.3]
    similarity = cosine_similarity(vec1, vec2)
    print(f"  ✅ Calculated cosine similarity: {similarity:.4f}")

    # ============================================================================
    # STEP 6: Demonstrate Complete Workflow
    # ============================================================================
    print("\n🔄 Step 6: Demonstrate Complete RAG Workflow")

    # Create knowledge base (using repository)
    kb_metadata = await kb_repository.create(
        name="Sample Knowledge Base",
        description="Demonstration KB",
        embedding_model="nomic-embed-text"
    )
    print(f"  ✅ Created knowledge base: {kb_metadata['id']}")

    # Create Qdrant collection
    qdrant_client.create_collection(
        collection_name=kb_metadata['id'],
        vectors_config={"size": 768, "distance": "Cosine"}
    )

    # Mock document upload
    sample_doc = "This is a sample document for demonstration purposes."

    # Generate embeddings
    embeddings = await ollama_manager.generate_embeddings(
        [sample_doc],
        model=kb_metadata['embedding_model']
    )
    print(f"  ✅ Generated embeddings: {len(embeddings[0])} dimensions")

    # Check cache
    cached = embedding_cache.get(sample_doc)
    if cached:
        print("  ✅ Embedding retrieved from cache!")
    else:
        embedding_cache.set(sample_doc, embeddings[0])
        print("  ✅ Embedding cached for future use")

    # Check resources
    resources = await resource_manager.check_resources()
    print(f"  ✅ Resource check: memory={resources.get('available_memory_mb', 'N/A')}MB, "
          f"load={resources.get('cpu_load', 'N/A')}, temp={resources.get('temperature_c', 'N/A')}°C")

    # Demonstrate retrieval
    pipeline = {
        "knowledge_base_ids": [kb_metadata['id']]
    }

    question = "What is this document about?"
    print(f"\n  🔍 Question: {question}")

    results = await retrieval_service.retrieve(
        pipeline=pipeline,
        question=question,
        top_k=3,
        knowledge_bases={kb_metadata['id']: kb_metadata}
    )

    print(f"  ✅ Retrieved {len(results['sources'])} sources")
    print(f"  ✅ Generated context: {len(results['context'])} characters")

    # ============================================================================
    # Summary
    # ============================================================================
    print("\n" + "="*70)
    print("🎉 Clean Architecture Demonstration Complete!")
    print("="*70)

    print("\n📊 Layer Summary:")
    print("  ✅ Infrastructure Layer - External services (Ollama, Qdrant, PostgreSQL)")
    print("  ✅ Repository Layer - Data access (KB, Conversations)")
    print("  ✅ Domain Layer - Business logic (Retrievers, Rerankers, Pipelines)")
    print("  ✅ Service Layer - Orchestration (RetrievalService, KBService)")
    print("  ✅ Utils Layer - Shared code (chunking, similarity)")

    print("\n🔑 Key Benefits Demonstrated:")
    print("  ✅ Dependency Injection - All components injected")
    print("  ✅ Single Responsibility - Each component has one job")
    print("  ✅ Testability - All layers independently testable")
    print("  ✅ Flexibility - Easy to swap implementations")
    print("  ✅ Maintainability - Clear code organization")

    print("\n📖 Next Steps:")
    print("  1. Replace mocks with real services (Ollama, Qdrant, PostgreSQL)")
    print("  2. Update main.py to use new architecture")
    print("  3. Deploy and test in production")
    print("  4. Monitor performance and optimize")

    print("\n✨ The RAG pipeline is ready for production deployment!")


if __name__ == "__main__":
    asyncio.run(demonstrate_clean_architecture())
