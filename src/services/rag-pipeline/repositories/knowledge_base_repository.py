"""
Knowledge Base Repository

Data access layer for knowledge base metadata.
Provides CRUD operations with PostgreSQL persistence.

This is a repository layer component for data access.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KnowledgeBaseRepository:
    """
    Knowledge base repository for data access

    Manages knowledge base metadata persistence with PostgreSQL.
    Provides CRUD operations for KB records.

    Features:
    - PostgreSQL-backed persistence
    - UUID-based IDs
    - Full CRUD operations
    - Type-safe operations

    Attributes:
        db_pool: PostgreSQL connection pool

    Example:
        >>> repo = KnowledgeBaseRepository(db_pool)
        >>> kb = repo.create(name="Docs", embedding_model="nomic-embed-text")
        >>> kbs = repo.list_all()
    """

    def __init__(self, db_pool: Any):
        """
        Initialize knowledge base repository

        Args:
            db_pool: PostgreSQL connection pool

        Raises:
            ValueError: If db_pool invalid
        """
        if db_pool is None:
            raise ValueError("db_pool cannot be None")

        self.db_pool = db_pool

        logger.info("✅ KnowledgeBaseRepository initialized")

    async def create(
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
        Create new knowledge base

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
            ValueError: If parameters invalid
            RuntimeError: If database operation fails
        """
        if not name:
            raise ValueError("name cannot be empty")

        if not embedding_model:
            raise ValueError("embedding_model cannot be empty")

        kb_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO knowledge_bases (id, name, description, embedding_model, llm_model, chunk_size, chunk_overlap, parent_child_enabled, document_count, vector_count, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    kb_id,
                    name,
                    description,
                    embedding_model,
                    llm_model,
                    chunk_size,
                    chunk_overlap,
                    parent_child_enabled,
                    0,
                    0,
                    created_at,
                )

            logger.info(f"✅ Created knowledge base in database: {kb_id}")

            return {
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
                "created_at": created_at,
            }

        except Exception as e:
            logger.error(f"❌ Failed to create knowledge base: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def get(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """
        Get knowledge base by ID

        Args:
            kb_id: Knowledge base ID

        Returns:
            Knowledge base metadata dict or None if not found

        Raises:
            ValueError: If kb_id invalid
        """
        if not kb_id:
            raise ValueError("kb_id cannot be empty")

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM knowledge_bases WHERE id = $1", kb_id
                )

            if not row:
                logger.warning(f"Knowledge base not found: {kb_id}")
                return None

            return dict(row)

        except Exception as e:
            logger.error(f"❌ Failed to get knowledge base: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def list_all(self) -> List[Dict[str, Any]]:
        """
        List all knowledge bases

        Returns:
            List of knowledge base metadata dicts

        Raises:
            RuntimeError: If database operation fails
        """
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM knowledge_bases ORDER BY created_at DESC"
                )

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"❌ Failed to list knowledge bases: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def update(
        self,
        kb_id: str,
        document_count: Optional[int] = None,
        vector_count: Optional[int] = None,
    ) -> bool:
        """
        Update knowledge base counters

        Args:
            kb_id: Knowledge base ID
            document_count: New document count (optional)
            vector_count: New vector count (optional)

        Returns:
            True if updated successfully

        Raises:
            ValueError: If kb_id invalid
            RuntimeError: If database operation fails
        """
        if not kb_id:
            raise ValueError("kb_id cannot be empty")

        if document_count is None and vector_count is None:
            raise ValueError("At least one field must be provided for update")

        try:
            async with self.db_pool.acquire() as conn:
                if document_count is not None and vector_count is not None:
                    await conn.execute(
                        """
                        UPDATE knowledge_bases
                        SET document_count = $1, vector_count = $2
                        WHERE id = $3
                        """,
                        document_count,
                        vector_count,
                        kb_id,
                    )
                elif document_count is not None:
                    await conn.execute(
                        "UPDATE knowledge_bases SET document_count = $1 WHERE id = $2",
                        document_count,
                        kb_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE knowledge_bases SET vector_count = $1 WHERE id = $2",
                        vector_count,
                        kb_id,
                    )

            logger.debug(f"✅ Updated knowledge base counters: {kb_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to update knowledge base: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def delete(self, kb_id: str) -> bool:
        """
        Delete knowledge base

        Args:
            kb_id: Knowledge base ID

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If kb_id invalid
            RuntimeError: If database operation fails
        """
        if not kb_id:
            raise ValueError("kb_id cannot be empty")

        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM knowledge_bases WHERE id = $1", kb_id
                )

            logger.info(f"✅ Deleted knowledge base: {kb_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to delete knowledge base: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def exists(self, kb_id: str) -> bool:
        """
        Check if knowledge base exists

        Args:
            kb_id: Knowledge base ID

        Returns:
            True if exists

        Raises:
            ValueError: If kb_id invalid
        """
        if not kb_id:
            raise ValueError("kb_id cannot be empty")

        try:
            kb = await self.get(kb_id)
            return kb is not None

        except Exception:
            return False
