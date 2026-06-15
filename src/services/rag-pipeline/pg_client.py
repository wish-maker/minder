"""
PostgreSQL Client for RAG Pipeline Persistence

Handles knowledge bases, pipelines, and conversation storage.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError as e:
    ASYNCPG_AVAILABLE = False
    logger.warning(f"⚠️  asyncpg not installed. PostgreSQL persistence will be disabled. Error: {e}")


# PostgreSQL availability flag
PG_AVAILABLE = ASYNCPG_AVAILABLE

# PostgreSQL connection pool
pg_pool: Optional[asyncpg.Pool] = None

# Database configuration
import os
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_USER = os.getenv("POSTGRES_USER", "minder")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "minder")
PG_DATABASE = os.getenv("POSTGRES_DATABASE", "minder")


async def get_pg_connection():
    """Get PostgreSQL connection from pool"""
    global pg_pool

    if not ASYNCPG_AVAILABLE:
        return None

    if pg_pool is None:
        try:
            # Create connection pool
            pg_pool = await asyncpg.create_pool(
                host=PG_HOST,
                port=int(PG_PORT),
                user=PG_USER,
                password=PG_PASSWORD,
                database=PG_DATABASE,
                min_size=2,
                max_size=10
            )
            logger.info(f"✅ PostgreSQL connection pool created: {PG_HOST}:{PG_PORT}/{PG_DATABASE}")
        except Exception as e:
            logger.error(f"❌ Failed to create PostgreSQL connection pool: {e}")
            raise

    return pg_pool


async def initialize_schema():
    """Initialize database schema for RAG pipeline"""
    try:
        conn = await get_pg_connection()
        if not conn:
            logger.warning("⚠️  PostgreSQL not available, skipping schema init")
            return False

        schema_sql = """
        -- Create tables if they don't exist (preserve existing data)
        CREATE TABLE IF NOT EXISTS knowledge_bases (
            id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            embedding_model VARCHAR(100) NOT NULL DEFAULT 'nomic-embed-text',
            llm_model VARCHAR(100) NOT NULL DEFAULT 'llama3',
            chunk_size INTEGER NOT NULL DEFAULT 512,
            chunk_overlap INTEGER NOT NULL DEFAULT 50,
            chunking_strategy VARCHAR(50) DEFAULT 'basic',
            parent_size INTEGER DEFAULT 2000,
            document_count INTEGER NOT NULL DEFAULT 0,
            vector_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS rag_pipelines (
            id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            knowledge_base_ids TEXT NOT NULL,
            retrieval_config TEXT,
            generation_config TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """

        async with conn.acquire() as connection:
            # Split and execute statements
            statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
            for statement in statements:
                await connection.execute(statement)

        logger.info("✅ Database schema initialized")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to initialize database schema: {e}")
        return False


async def save_kb_to_postgres(kb_id: str, kb_data: Dict[str, Any]) -> bool:
    """Save knowledge base to PostgreSQL"""
    try:
        conn = await get_pg_connection()
        if not conn:
            return False

        async with conn.acquire() as connection:
            await connection.execute("""
                INSERT INTO knowledge_bases
                (id, name, description, embedding_model, llm_model, chunk_size, chunk_overlap, chunking_strategy, parent_size, document_count, vector_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    embedding_model = EXCLUDED.embedding_model,
                    llm_model = EXCLUDED.llm_model,
                    chunk_size = EXCLUDED.chunk_size,
                    chunk_overlap = EXCLUDED.chunk_overlap,
                    chunking_strategy = EXCLUDED.chunking_strategy,
                    parent_size = EXCLUDED.parent_size,
                    document_count = EXCLUDED.document_count,
                    vector_count = EXCLUDED.vector_count,
                    updated_at = CURRENT_TIMESTAMP
            """, kb_id, kb_data["name"], kb_data.get("description", ""), kb_data["embedding_model"],
                kb_data["llm_model"], kb_data["chunk_size"], kb_data["chunk_overlap"],
                kb_data.get("chunking_strategy", "basic"), kb_data.get("parent_size", 2000),
                kb_data["document_count"], kb_data["vector_count"])

        logger.info(f"✅ KB saved to PostgreSQL: {kb_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to save KB to PostgreSQL: {e}")
        return False


async def load_kb_from_postgres() -> Dict[str, Dict[str, Any]]:
    """Load all knowledge bases from PostgreSQL"""
    try:
        conn = await get_pg_connection()
        if not conn:
            return {}

        async with conn.acquire() as connection:
            rows = await connection.fetch("""
                SELECT id, name, description, embedding_model, llm_model, chunk_size, chunk_overlap, chunking_strategy, parent_size, document_count, vector_count, created_at
                FROM knowledge_bases
                ORDER BY created_at DESC
            """)

        kbs = {}
        for row in rows:
            kb_id = str(row["id"])  # Convert UUID to string
            kbs[kb_id] = {
                "id": kb_id,
                "name": row["name"],
                "description": row["description"],
                "embedding_model": row["embedding_model"],
                "llm_model": row["llm_model"],
                "chunk_size": row["chunk_size"],
                "chunk_overlap": row["chunk_overlap"],
                "chunking_strategy": row["chunking_strategy"],
                "parent_size": row["parent_size"],
                "document_count": row["document_count"],
                "vector_count": row["vector_count"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "persisted": True  # Mark as loaded from PostgreSQL
            }

        logger.info(f"✅ Loaded {len(kbs)} KBs from PostgreSQL")
        return kbs

    except Exception as e:
        logger.error(f"❌ Failed to load KBs from PostgreSQL: {e}")
        return {}


async def save_pipeline_to_postgres(pipeline_id: str, pipeline_data: Dict[str, Any]) -> bool:
    """Save RAG pipeline to PostgreSQL"""
    try:
        conn = await get_pg_connection()
        if not conn:
            return False

        # Convert knowledge_base_ids list to PostgreSQL array format
        kb_ids = pipeline_data["knowledge_base_ids"]
        if isinstance(kb_ids, list):
            # Store as JSON string for TEXT type or as PostgreSQL array
            kb_ids_str = json.dumps(kb_ids)  # Serialize to JSON string
        else:
            kb_ids_str = str(kb_ids)

        async with conn.acquire() as connection:
            await connection.execute("""
                INSERT INTO rag_pipelines
                (id, name, knowledge_base_ids, retrieval_config, generation_config)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    knowledge_base_ids = EXCLUDED.knowledge_base_ids,
                    retrieval_config = EXCLUDED.retrieval_config,
                    generation_config = EXCLUDED.generation_config,
                    updated_at = CURRENT_TIMESTAMP
            """, pipeline_id, pipeline_data["name"], kb_ids_str,
                json.dumps(pipeline_data.get("retrieval_config", {})),
                json.dumps(pipeline_data.get("generation_config", {})))

        logger.info(f"✅ Pipeline saved to PostgreSQL: {pipeline_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to save pipeline to PostgreSQL: {e}")
        return False


async def load_pipelines_from_postgres() -> Dict[str, Dict[str, Any]]:
    """Load all RAG pipelines from PostgreSQL"""
    try:
        conn = await get_pg_connection()
        if not conn:
            return {}

        async with conn.acquire() as connection:
            rows = await connection.fetch("""
                SELECT id, name, knowledge_base_ids, retrieval_config, generation_config, created_at
                FROM rag_pipelines
                ORDER BY created_at DESC
            """)

        pipelines = {}
        for row in rows:
            pipeline_id = str(row["id"])  # Convert UUID to string
            kb_ids = row["knowledge_base_ids"]
            logger.debug(f"Raw KB IDs from PostgreSQL: {kb_ids}, type: {type(kb_ids)}")

            # Handle knowledge_base_ids - now stored as JSON string
            if kb_ids:
                try:
                    # Parse JSON string back to list
                    if isinstance(kb_ids, str):
                        kb_ids_list = json.loads(kb_ids)
                    else:
                        # Fallback for PostgreSQL array type
                        kb_ids_list = [str(kb_id) for kb_id in kb_ids]
                except Exception as e:
                    logger.warning(f"Failed to parse KB IDs: {e}")
                    kb_ids_list = []
            else:
                kb_ids_list = []

            pipelines[pipeline_id] = {
                "id": pipeline_id,
                "name": row["name"],
                "knowledge_base_ids": kb_ids_list,
                "retrieval_config": json.loads(row["retrieval_config"]) if row["retrieval_config"] else {},
                "generation_config": json.loads(row["generation_config"]) if row["generation_config"] else {},
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "persisted": True  # Mark as loaded from PostgreSQL
            }
            logger.debug(f"Loaded pipeline {pipeline_id} with KBs: {kb_ids_list}")

        logger.info(f"✅ Loaded {len(pipelines)} pipelines from PostgreSQL")
        return pipelines

    except Exception as e:
        logger.error(f"❌ Failed to load pipelines from PostgreSQL: {e}")
        return {}


async def save_session_to_postgres(session_id: str, session_data: Dict[str, Any]) -> bool:
    """Save conversation session to PostgreSQL"""
    try:
        conn = await get_pg_connection()
        if not conn:
            return False

        async with conn.acquire() as connection:
            await connection.execute("""
                INSERT INTO conversation_sessions
                (session_id, user_id, pipeline_id, message_count, metadata, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (session_id) DO UPDATE SET
                    message_count = EXCLUDED.message_count,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
            """, session_id, session_data.get("user_id"), session_data.get("pipeline_id"),
                session_data.get("message_count", 0), json.dumps(session_data.get("metadata", {})),
                session_data.get("expires_at"))

        logger.info(f"✅ Session saved to PostgreSQL: {session_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to save session to PostgreSQL: {e}")
        return False


async def save_conversation_turn_to_postgres(
    session_id: str,
    turn_id: str,
    question: str,
    answer: str,
    sources: List[Dict] = None,
    confidence: float = None,
    embedding: List[float] = None
) -> bool:
    """Save conversation turn to PostgreSQL"""
    try:
        conn = await get_pg_connection()
        if not conn:
            return False

        async with conn.acquire() as connection:
            # Store embedding as array if available
            embedding_array = embedding if embedding else None

            await connection.execute("""
                INSERT INTO conversation_turns
                (session_id, turn_id, question, answer, sources, confidence, embedding, timestamp)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, session_id, turn_id, question, answer,
                json.dumps(sources) if sources else None,
                confidence,
                embedding_array,
                datetime.utcnow())

        logger.debug(f"✅ Conversation turn saved to PostgreSQL: {turn_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to save conversation turn to PostgreSQL: {e}")
        return False
