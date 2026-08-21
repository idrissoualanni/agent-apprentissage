-- Agent d'Apprentissage — Schéma SQLite V1
-- Persistance : profil, compétences, mastery, sessions, quiz, restitutions Feynman

-- Profil apprenant (mono-utilisateur V1)
CREATE TABLE IF NOT EXISTS learner_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    domain TEXT NOT NULL DEFAULT '',
    niveau_global TEXT CHECK (niveau_global IN ('debutant', 'intermediaire', 'avance', '')),
    updated_at DATETIME DEFAULT (datetime('now'))
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

-- Sessions de conversation
CREATE TABLE IF NOT EXISTS session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    langgraph_thread_id TEXT NOT NULL UNIQUE,
    started_at DATETIME DEFAULT (datetime('now')),
    ended_at DATETIME
);

-- Messages dans les sessions
CREATE TABLE IF NOT EXISTS message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    method_used TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Tentatives de quiz
CREATE TABLE IF NOT EXISTS quiz_attempt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    options TEXT,
    user_answer TEXT,
    is_correct BOOLEAN,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Restitutions Feynman
CREATE TABLE IF NOT EXISTS feynman_restitution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
    user_explanation TEXT NOT NULL,
    agent_evaluation TEXT,
    score REAL CHECK (score >= 0.0 AND score <= 1.0),
    gaps_identified TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Index pour performance
CREATE INDEX IF NOT EXISTS idx_mastery_competency ON mastery(competency_id);
CREATE INDEX IF NOT EXISTS idx_mastery_next_review ON mastery(next_review_at);
CREATE INDEX IF NOT EXISTS idx_mastery_status ON mastery(status);
CREATE INDEX IF NOT EXISTS idx_chunk_document ON chunk(document_id);
CREATE INDEX IF NOT EXISTS idx_chunk_competency ON chunk(competency_id);
CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id);
CREATE INDEX IF NOT EXISTS idx_quiz_competency ON quiz_attempt(competency_id);
CREATE INDEX IF NOT EXISTS idx_feynman_competency ON feynman_restitution(competency_id);

-- Trigger : MAJ updated_at du profil à chaque insertion de restitution
CREATE TRIGGER IF NOT EXISTS trg_update_profile_after_restitution
AFTER INSERT ON feynman_restitution
BEGIN
    UPDATE learner_profile SET updated_at = datetime('now') WHERE id = 1;
END;

-- Trigger : MAJ updated_at du profil à chaque tentative de quiz
CREATE TRIGGER IF NOT EXISTS trg_update_profile_after_quiz
AFTER INSERT ON quiz_attempt
BEGIN
    UPDATE learner_profile SET updated_at = datetime('now') WHERE id = 1;
END;
