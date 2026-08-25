-- Agent d'Apprentissage — Schéma SQLite V3
-- Évolution V1 → V3 : multi-user, artifacts, model configs, web search cache, tool usage

-- ═══════════════════════════════════════════════════════════════════════════
-- TABLES V3 (nouvelles)
-- ═══════════════════════════════════════════════════════════════════════════

-- Profil apprenant (multi-user V3)
CREATE TABLE IF NOT EXISTS learner_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    domain TEXT NOT NULL DEFAULT '',
    niveau_global TEXT CHECK (niveau_global IN ('debutant', 'intermediaire', 'avance', '')),
    learning_context TEXT DEFAULT '',
    goals TEXT DEFAULT '',
    mastered_topics TEXT DEFAULT '',
    learning_topics TEXT DEFAULT '',
    gap_topics TEXT DEFAULT '',
    updated_at DATETIME DEFAULT (datetime('now')),
    UNIQUE(user_id)
);

-- Arbre de compétences (auto-référencée pour hiérarchie)
CREATE TABLE IF NOT EXISTS competency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    nom TEXT NOT NULL,
    parent_id INTEGER REFERENCES competency(id) ON DELETE SET NULL,
    description TEXT,
    UNIQUE(domain, nom)
);

-- Maîtrise par compétence + Leitner
CREATE TABLE IF NOT EXISTS mastery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0.0 CHECK (score >= 0.0 AND score <= 1.0),
    leitner_box INTEGER NOT NULL DEFAULT 0 CHECK (leitner_box >= 0 AND leitner_box <= 5),
    last_reviewed_at DATETIME,
    next_review_at DATETIME,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'learning', 'acquired', 'review')),
    UNIQUE(competency_id)
);

-- Documents PDF importés
CREATE TABLE IF NOT EXISTS document (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    uploaded_at DATETIME DEFAULT (datetime('now')),
    num_chunks INTEGER DEFAULT 0
);

-- Chunks (lien vers ChromaDB via chroma_vector_id)
CREATE TABLE IF NOT EXISTS chunk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section_title TEXT,
    chroma_vector_id TEXT,
    competency_id INTEGER REFERENCES competency(id) ON DELETE SET NULL,
    UNIQUE(document_id, chunk_index)
);

-- Sessions de conversation (multi-user V3)
CREATE TABLE IF NOT EXISTS session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    langgraph_thread_id TEXT NOT NULL UNIQUE,
    title TEXT DEFAULT '',
    started_at DATETIME DEFAULT (datetime('now')),
    ended_at DATETIME
);

-- Messages dans les sessions (multi-user V3)
CREATE TABLE IF NOT EXISTS message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    method_used TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Tentatives de quiz (multi-user V3)
CREATE TABLE IF NOT EXISTS quiz_attempt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    question TEXT NOT NULL,
    options TEXT,
    user_answer TEXT,
    is_correct BOOLEAN,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Restitutions Feynman (multi-user V3)
CREATE TABLE IF NOT EXISTS feynman_restitution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    user_explanation TEXT NOT NULL,
    agent_evaluation TEXT,
    score REAL CHECK (score >= 0.0 AND score <= 1.0),
    gaps_identified TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════════════════
-- NOUVELLES TABLES V3
-- ═══════════════════════════════════════════════════════════════════════════

-- Artefacts générés (schemas Mermaid, quiz React, code, charts)
CREATE TABLE IF NOT EXISTS artifact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK (type IN ('schema', 'quiz', 'code', 'chart')),
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '{}',
    format TEXT NOT NULL DEFAULT 'json',
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Configuration des modèles (persistance du catalogue)
CREATE TABLE IF NOT EXISTS model_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'ollama_local',
    default_temperature REAL DEFAULT 0.3,
    format_mode TEXT NOT NULL DEFAULT 'json_or_markdown',
    max_tokens INTEGER DEFAULT 2048,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Cache des recherches web
CREATE TABLE IF NOT EXISTS web_search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT NOT NULL UNIQUE,
    query TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'ddgs',
    results TEXT NOT NULL DEFAULT '[]',
    fetched_at DATETIME DEFAULT (datetime('now'))
);

-- Suivi d'utilisation des outils (transparence)
CREATE TABLE IF NOT EXISTS tool_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    tool_name TEXT NOT NULL,
    input_summary TEXT DEFAULT '',
    output_summary TEXT DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now'))
);

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
-- TRIGGERS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TRIGGER IF NOT EXISTS trg_update_profile_after_restitution
AFTER INSERT ON feynman_restitution
BEGIN
    UPDATE learner_profile SET updated_at = datetime('now')
    WHERE user_id = NEW.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_update_profile_after_quiz
AFTER INSERT ON quiz_attempt
BEGIN
    UPDATE learner_profile SET updated_at = datetime('now')
    WHERE user_id = NEW.user_id;
END;
