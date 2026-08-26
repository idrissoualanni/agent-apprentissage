-- Agent d'Apprentissage — Schema PostgreSQL V3 (Neon)
-- Equivalent de schema_v3.sql, adapte pour PostgreSQL.

-- ═══════════════════════════════════════════════════════════════════════════
-- TABLES
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS learner_profile (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    domain TEXT NOT NULL DEFAULT '',
    niveau_global TEXT CHECK (niveau_global IN ('debutant', 'intermediaire', 'avance', '')),
    learning_context TEXT DEFAULT '',
    goals TEXT DEFAULT '',
    mastered_topics TEXT DEFAULT '',
    learning_topics TEXT DEFAULT '',
    gap_topics TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE TABLE IF NOT EXISTS competency (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    nom TEXT NOT NULL,
    parent_id INTEGER REFERENCES competency(id) ON DELETE SET NULL,
    description TEXT,
    UNIQUE(domain, nom)
);

CREATE TABLE IF NOT EXISTS mastery (
    id SERIAL PRIMARY KEY,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0.0 CHECK (score >= 0.0 AND score <= 1.0),
    leitner_box INTEGER NOT NULL DEFAULT 0 CHECK (leitner_box >= 0 AND leitner_box <= 5),
    last_reviewed_at TIMESTAMP,
    next_review_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'learning', 'acquired', 'review')),
    UNIQUE(competency_id)
);

CREATE TABLE IF NOT EXISTS document (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    num_chunks INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunk (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section_title TEXT,
    chroma_vector_id TEXT,
    competency_id INTEGER REFERENCES competency(id) ON DELETE SET NULL,
    UNIQUE(document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS session (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    langgraph_thread_id TEXT NOT NULL UNIQUE,
    title TEXT DEFAULT '',
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    method_used TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quiz_attempt (
    id SERIAL PRIMARY KEY,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    question TEXT NOT NULL,
    options TEXT,
    user_answer TEXT,
    is_correct BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feynman_restitution (
    id SERIAL PRIMARY KEY,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    user_explanation TEXT NOT NULL,
    agent_evaluation TEXT,
    score REAL CHECK (score >= 0.0 AND score <= 1.0),
    gaps_identified TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS artifact (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK (type IN ('schema', 'quiz', 'code', 'chart')),
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '{}',
    format TEXT NOT NULL DEFAULT 'json',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS model_config (
    id SERIAL PRIMARY KEY,
    model_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'ollama_local',
    default_temperature REAL DEFAULT 0.3,
    format_mode TEXT NOT NULL DEFAULT 'json_or_markdown',
    max_tokens INTEGER DEFAULT 2048,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS web_search_cache (
    id SERIAL PRIMARY KEY,
    query_hash TEXT NOT NULL UNIQUE,
    query TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'ddgs',
    results TEXT NOT NULL DEFAULT '[]',
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tool_usage (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    tool_name TEXT NOT NULL,
    input_summary TEXT DEFAULT '',
    output_summary TEXT DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- TABLES MEMOIRE (Phase 2 — Learner Model)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS session_competency_score (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    session_id INTEGER REFERENCES session(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0.0,
    p_success REAL DEFAULT 0.5,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(session_id, competency_id)
);

CREATE TABLE IF NOT EXISTS method_effectiveness (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    competency_id INTEGER REFERENCES competency(id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    uses INTEGER DEFAULT 1,
    successes INTEGER DEFAULT 0,
    effectiveness REAL DEFAULT 0.0,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(competency_id, method)
);

CREATE TABLE IF NOT EXISTS user_topic_history (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    topic TEXT NOT NULL,
    mentions INTEGER DEFAULT 1,
    last_mentioned TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, topic)
);

CREATE TABLE IF NOT EXISTS session_summary (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES session(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    pedagogical_facts TEXT DEFAULT '{}',
    text_summary TEXT DEFAULT '',
    turn_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(session_id)
);

CREATE TABLE IF NOT EXISTS pending_competency (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    proposed_name TEXT NOT NULL,
    proposed_domain TEXT DEFAULT '',
    parent_competency_id INTEGER REFERENCES competency(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scs_session ON session_competency_score(session_id);
CREATE INDEX IF NOT EXISTS idx_scs_competency ON session_competency_score(competency_id);
CREATE INDEX IF NOT EXISTS idx_me_competency ON method_effectiveness(competency_id);
CREATE INDEX IF NOT EXISTS idx_uth_user ON user_topic_history(user_id);
CREATE INDEX IF NOT EXISTS idx_ss_session ON session_summary(session_id);
CREATE INDEX IF NOT EXISTS idx_pc_user ON pending_competency(user_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- INDEX
-- ═══════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_mastery_competency ON mastery(competency_id);
CREATE INDEX IF NOT EXISTS idx_mastery_next_review ON mastery(next_review_at);
CREATE INDEX IF NOT EXISTS idx_mastery_status ON mastery(status);
CREATE INDEX IF NOT EXISTS idx_chunk_document ON chunk(document_id);
CREATE INDEX IF NOT EXISTS idx_chunk_competency ON chunk(competency_id);
CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id);
CREATE INDEX IF NOT EXISTS idx_message_user ON message(user_id);
CREATE INDEX IF NOT EXISTS idx_quiz_competency ON quiz_attempt(competency_id);
CREATE INDEX IF NOT EXISTS idx_quiz_user ON quiz_attempt(user_id);
CREATE INDEX IF NOT EXISTS idx_feynman_competency ON feynman_restitution(competency_id);
CREATE INDEX IF NOT EXISTS idx_feynman_user ON feynman_restitution(user_id);
CREATE INDEX IF NOT EXISTS idx_session_user ON session(user_id);
CREATE INDEX IF NOT EXISTS idx_artifact_user ON artifact(user_id);
CREATE INDEX IF NOT EXISTS idx_artifact_session ON artifact(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_usage_user ON tool_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON tool_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_web_search_hash ON web_search_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_model_config_name ON model_config(model_name);

-- ═══════════════════════════════════════════════════════════════════════════
-- TRIGGERS (equivalent PostgreSQL des triggers SQLite)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION update_profile_timestamp() RETURNS TRIGGER AS $$
BEGIN
    UPDATE learner_profile SET updated_at = NOW() WHERE user_id = NEW.user_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_profile_after_restitution ON feynman_restitution;
CREATE TRIGGER trg_update_profile_after_restitution
AFTER INSERT ON feynman_restitution
FOR EACH ROW EXECUTE FUNCTION update_profile_timestamp();

DROP TRIGGER IF EXISTS trg_update_profile_after_quiz ON quiz_attempt;
CREATE TRIGGER trg_update_profile_after_quiz
AFTER INSERT ON quiz_attempt
FOR EACH ROW EXECUTE FUNCTION update_profile_timestamp();

-- ═══════════════════════════════════════════════════════════════════════════
-- DONNEES INITIALES
-- ═══════════════════════════════════════════════════════════════════════════

INSERT INTO learner_profile (user_id, domain, niveau_global)
VALUES ('default_user', '', '')
ON CONFLICT (user_id) DO NOTHING;
