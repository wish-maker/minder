-- rag-pipeline database schema (issue #17)
-- Knowledge bases, pipelines, and conversational-RAG turn history.

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

-- #943: the JWT `sub` of the user who created the pipeline, so queries and the
-- OpenWebUI chat-tool synthesis can be owner-scoped (a user must not query, or
-- see as an `ask_*` tool, a knowledge base someone else created). Nullable:
-- pipelines created before this migration have no recorded owner and stay
-- open (legacy/shared) rather than becoming unqueryable.
ALTER TABLE rag_pipelines
    ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(255);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    conversation_id VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_lookup
ON conversation_turns(user_id, conversation_id, timestamp DESC);

-- Conversations are per-user by default (#875) -- a row here is the explicit
-- opt-in for a conversation_id to become a shared/collaborative thread: every
-- turn under this conversation_id is then read from and written to
-- owner_user_id's bucket regardless of who's actually asking, instead of each
-- participant's own private history.
CREATE TABLE IF NOT EXISTS conversation_shares (
    conversation_id VARCHAR(255) PRIMARY KEY,
    owner_user_id VARCHAR(255) NOT NULL,
    shared_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- The real first-writer of a conversation_id (#893) -- a client-supplied,
-- globally-namespaced string with no per-user uniqueness, so a SECOND user
-- can legitimately store their own private turn under the SAME conversation_id
-- another user already started (per-user-private-by-default, #875). Ownership
-- must therefore be recorded atomically at the true first write (store_turn's
-- `ON CONFLICT (conversation_id) DO NOTHING` below -- whoever's insert lands
-- first wins the row, every later writer's insert is a no-op), not derived
-- after the fact from "has this user ever written here," which any later
-- writer would also satisfy.
CREATE TABLE IF NOT EXISTS conversation_owners (
    conversation_id VARCHAR(255) PRIMARY KEY,
    owner_user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
