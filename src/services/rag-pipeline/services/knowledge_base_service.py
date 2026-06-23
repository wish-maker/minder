"""
Knowledge Base Service

Manages knowledge base CRUD operations and document ingestion.
Orchestrates chunking, embedding generation, and vector storage.

This is a service layer component that orchestrates domain + infrastructure.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """
    Knowledge base management service

    Handles:
    - Knowledge base creation and management
    - Document ingestion with chunking
    - Embedding generation and vector storage
    - Parent-child hierarchical chunking support

    Features:
    - KB creation with Qdrant collection
    - Document upload with text extraction
    - Parent-child hierarchical chunking
    - Batch embedding generation
    - Vector storage in Qdrant

    Attributes:
        ollama_manager: LLM and embedding service
        qdrant_client: Vector database client
        parent_child_chunker: Parent-child chunker (optional)

    Example:
        >>> service = KnowledgeBaseService(
        ...     ollama_manager=ollama,
        ...     qdrant_client=qdrant,
        ...     parent_child_chunker=chunker
        ... )
        >>> kb = await service.create_knowledge_base(
        ...     name="Technical Docs",
        ...     embedding_model="nomic-embed-text"
        ... )
    """

    def __init__(
        self,
        ollama_manager: Any,
        qdrant_client: Any,
        parent_child_chunker: Any = None,
        embedding_dimensions: Dict[str, int] = None,
    ):
        """
        Initialize knowledge base service

        Args:
            ollama_manager: LLM and embedding service
            qdrant_client: Vector database client
            parent_child_chunker: Optional parent-child chunker
            embedding_dimensions: Model embedding dimensions mapping

        Note:
            embedding_dimensions defaults to standard models if not provided
        """
        self.ollama_manager = ollama_manager
        self.qdrant_client = qdrant_client
        self.parent_child_chunker = parent_child_chunker
        self.embedding_dimensions = embedding_dimensions or {
            "nomic-embed-text": 768,
            "mxbai-embed-large": 1024,
            "all-minilm": 384,
        }

        logger.info("✅ KnowledgeBaseService initialized")

    def create_knowledge_base(
        self,
        name: str,
        description: str = "",
        embedding_model: str = "nomic-embed-text",
        llm_model: str = "llama3",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        parent_child_enabled: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a new knowledge base

        Args:
            name: Knowledge base name
            description: Optional description
            embedding_model: Embedding model name
            llm_model: LLM model name
            chunk_size: Text chunk size
            chunk_overlap: Chunk overlap size
            parent_child_enabled: Enable parent-child chunking

        Returns:
            Knowledge base metadata dict

        Raises:
            ValueError: If name or embedding_model invalid
        """
        if not name:
            raise ValueError("name cannot be empty")

        if not embedding_model:
            raise ValueError("embedding_model cannot be empty")

        kb_id = str(uuid.uuid4())

        # Get embedding dimension
        embed_dim = self.embedding_dimensions.get(embedding_model, 768)

        # Create KB metadata
        kb_metadata = {
            "id": kb_id,
            "name": name,
            "description": description,
            "embedding_model": embedding_model,
            "llm_model": llm_model,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "parent_child_enabled": parent_child_enabled,
            "document_count": 0,
            "vector_count": 0,
            "created_at": datetime.now().isoformat(),
        }

        # Create Qdrant collection
        try:
            from qdrant_client.models import Distance, VectorParams

            self.qdrant_client.create_collection(
                collection_name=kb_id,
                vectors_config=VectorParams(size=embed_dim, distance=Distance.COSINE),
            )
            logger.info(f"✅ Created Qdrant collection: {kb_id} (dim={embed_dim})")

        except Exception as e:
            logger.error(f"❌ Failed to create Qdrant collection: {e}")
            raise ValueError(f"Failed to create collection: {str(e)}")

        logger.info(f"✅ Created knowledge base: {kb_id} - {name}")

        return kb_metadata

    def list_knowledge_bases(
        self, knowledge_bases: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        List all knowledge bases

        Args:
            knowledge_bases: Knowledge base metadata dictionary

        Returns:
            List of knowledge base metadata dicts
        """
        return list(knowledge_bases.values())

    def get_knowledge_base(
        self, kb_id: str, knowledge_bases: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Get knowledge base by ID

        Args:
            kb_id: Knowledge base ID
            knowledge_bases: Knowledge base metadata dictionary

        Returns:
            Knowledge base metadata dict

        Raises:
            ValueError: If kb_id not found
        """
        if kb_id not in knowledge_bases:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        return knowledge_bases[kb_id]

    async def upload_document(
        self,
        kb_id: str,
        content: bytes,
        filename: str,
        knowledge_bases: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Upload document to knowledge base

        Args:
            kb_id: Knowledge base ID
            content: File content bytes
            filename: Original filename
            knowledge_bases: Knowledge base metadata dictionary

        Returns:
            Upload result dict with chunk_count, vector_count

        Raises:
            ValueError: If kb_id not found or content invalid
        """
        if kb_id not in knowledge_bases:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        kb = knowledge_bases[kb_id]

        if not content:
            raise ValueError("content cannot be empty")

        logger.info(f"📄 Uploading document: {filename} to KB {kb_id}")

        # Extract text from file
        text = await self._extract_text_from_file(content, filename)

        if not text or len(text.strip()) < 10:
            raise ValueError("No valid text content extracted")

        # Chunk text (with parent-child support)
        chunks = await self._chunk_text(text, kb, kb_id)

        if not chunks:
            raise ValueError("No chunks generated from text")

        logger.info(f"✅ Generated {len(chunks)} chunks")

        # Generate embeddings
        embeddings = await self.ollama_manager.generate_embeddings(
            chunks, model=kb["embedding_model"]
        )

        # Store in Qdrant
        chunk_count = await self._store_vectors(kb_id, chunks, embeddings, filename)

        # Update KB metadata
        kb["document_count"] += 1
        kb["vector_count"] += chunk_count

        logger.info(f"✅ Document uploaded: {chunk_count} vectors stored")

        return {
            "kb_id": kb_id,
            "filename": filename,
            "chunk_count": chunk_count,
            "vector_count": chunk_count,
        }

    async def _extract_text_from_file(self, content: bytes, filename: str) -> str:
        """
        Extract text from file based on type

        Args:
            content: File content bytes
            filename: Original filename

        Returns:
            Extracted text string

        Raises:
            ValueError: If text extraction fails
        """
        import io

        try:
            from pypdf import PdfReader

            if filename.endswith(".pdf"):
                pdf_file = io.BytesIO(content)
                reader = PdfReader(pdf_file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text

            elif filename.endswith(".txt") or filename.endswith(".md"):
                return content.decode("utf-8")

            else:
                # Default: try UTF-8 decode
                try:
                    return content.decode("utf-8")
                except UnicodeDecodeError:
                    return content.decode("latin-1")

        except Exception as e:
            logger.error(f"❌ Text extraction failed: {e}")
            raise ValueError(f"Failed to extract text: {str(e)}")

    async def _chunk_text(self, text: str, kb: Dict[str, Any], kb_id: str) -> List[str]:
        """
        Chunk text using appropriate strategy

        Args:
            text: Text to chunk
            kb: Knowledge base metadata
            kb_id: Knowledge base ID

        Returns:
            List of text chunks

        Raises:
            ValueError: If chunking fails
        """
        try:
            # Parent-child hierarchical chunking
            if kb.get("parent_child_enabled", False) and self.parent_child_chunker:
                hierarchy = self.parent_child_chunker.create_hierarchy(text)

                # Index for parent-child retrieval
                from domain import ParentChildRetriever

                retriever = ParentChildRetriever()
                retriever.index_hierarchy(kb_id, hierarchy)

                # Use child chunks for embeddings
                chunks = [item["text"] for item in hierarchy if item["type"] == "child"]
                logger.info(
                    f"✅ Parent-child chunking: {len(hierarchy)} total ({len(chunks)} children)"
                )
                return chunks

            # Regular chunking
            else:
                from langchain_text_splitters import RecursiveCharacterTextSplitter

                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=kb["chunk_size"],
                    chunk_overlap=kb["chunk_overlap"],
                    length_function=len,
                )

                chunks = text_splitter.split_text(text)
                logger.info(f"✅ Regular chunking: {len(chunks)} chunks")
                return chunks

        except Exception as e:
            logger.error(f"❌ Chunking failed: {e}")
            raise ValueError(f"Chunking failed: {str(e)}")

    async def _store_vectors(
        self,
        kb_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        filename: str,
    ) -> int:
        """
        Store vectors in Qdrant

        Args:
            kb_id: Knowledge base ID
            chunks: Text chunks
            embeddings: Embedding vectors
            filename: Source filename

        Returns:
            Number of vectors stored

        Raises:
            ValueError: If storage fails
        """
        try:
            from qdrant_client.models import PointStruct

            points = []

            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={
                        "text": chunk,
                        "source": filename,
                        "_id": f"{filename}_{i}",
                    },
                )
                points.append(point)

            # Batch upsert
            self.qdrant_client.upsert(collection_name=kb_id, points=points)

            return len(points)

        except Exception as e:
            logger.error(f"❌ Vector storage failed: {e}")
            raise ValueError(f"Vector storage failed: {str(e)}")
