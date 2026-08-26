"""Migrations V3 — détection automatique + application idempotente."""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA_V3_PATH = Path(__file__).resolve().parent / "schema_v3.sql"


def _get_existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def _get_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _get_existing_indexes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def _get_existing_triggers(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    return {r[0] for r in rows}


# ─── Nouvelles colonnes V3 par table ─────────────────────────────────────

V3_COLUMNS: dict[str, dict[str, str]] = {
    "learner_profile": {
        "user_id": "TEXT NOT NULL DEFAULT 'default_user'",
        "learning_context": "TEXT DEFAULT ''",
        "goals": "TEXT DEFAULT ''",
        "mastered_topics": "TEXT DEFAULT ''",
        "learning_topics": "TEXT DEFAULT ''",
        "gap_topics": "TEXT DEFAULT ''",
    },
    "session": {
        "user_id": "TEXT NOT NULL DEFAULT 'default_user'",
        "title": "TEXT DEFAULT ''",
    },
    "message": {
        "user_id": "TEXT NOT NULL DEFAULT 'default_user'",
    },
    "quiz_attempt": {
        "user_id": "TEXT NOT NULL DEFAULT 'default_user'",
    },
    "feynman_restitution": {
        "user_id": "TEXT NOT NULL DEFAULT 'default_user'",
    },
}

# ─── Nouvelles tables V3 ─────────────────────────────────────────────────

V3_TABLES: dict[str, str] = {
    "artifact": """
        CREATE TABLE IF NOT EXISTS artifact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default_user',
            session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,
            type TEXT NOT NULL CHECK (type IN ('schema', 'quiz', 'code', 'chart')),
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '{}',
            format TEXT NOT NULL DEFAULT 'json',
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """,
    "model_config": """
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
        )
    """,
    "web_search_cache": """
        CREATE TABLE IF NOT EXISTS web_search_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT NOT NULL UNIQUE,
            query TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'ddgs',
            results TEXT NOT NULL DEFAULT '[]',
            fetched_at DATETIME DEFAULT (datetime('now'))
        )
    """,
    "tool_usage": """
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
        )
    """,
}

V3_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_message_user ON message(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_quiz_user ON quiz_attempt(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_feynman_user ON feynman_restitution(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_session_user ON session(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifact_user ON artifact(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifact_session ON artifact(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_tool_usage_user ON tool_usage(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON tool_usage(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_web_search_hash ON web_search_cache(query_hash)",
    "CREATE INDEX IF NOT EXISTS idx_model_config_name ON model_config(model_name)",
]

V3_TRIGGERS: list[str] = [
    """CREATE TRIGGER IF NOT EXISTS trg_update_profile_after_restitution
       AFTER INSERT ON feynman_restitution
       BEGIN
           UPDATE learner_profile SET updated_at = datetime('now')
           WHERE user_id = NEW.user_id;
       END""",
    """CREATE TRIGGER IF NOT EXISTS trg_update_profile_after_quiz
       AFTER INSERT ON quiz_attempt
       BEGIN
           UPDATE learner_profile SET updated_at = datetime('now')
           WHERE user_id = NEW.user_id;
       END""",
]


# ─── Tables mémoire (Phase 2 — Learner Model) ────────────────────────────
# Base de connaissance utilisateur : score par compétence/session, efficacité
# des méthodes, sujets habituels, résumé de session, compétences en attente.

MEMORY_TABLES: dict[str, str] = {
    "session_competency_score": """
        CREATE TABLE IF NOT EXISTS session_competency_score (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default_user',
            session_id INTEGER REFERENCES session(id) ON DELETE CASCADE,
            competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
            score REAL NOT NULL DEFAULT 0.0,
            p_success REAL DEFAULT 0.5,
            updated_at DATETIME DEFAULT (datetime('now')),
            UNIQUE(session_id, competency_id)
        )
    """,
    "method_effectiveness": """
        CREATE TABLE IF NOT EXISTS method_effectiveness (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default_user',
            competency_id INTEGER REFERENCES competency(id) ON DELETE CASCADE,
            method TEXT NOT NULL,
            uses INTEGER DEFAULT 1,
            successes INTEGER DEFAULT 0,
            effectiveness REAL DEFAULT 0.0,
            updated_at DATETIME DEFAULT (datetime('now')),
            UNIQUE(competency_id, method)
        )
    """,
    "user_topic_history": """
        CREATE TABLE IF NOT EXISTS user_topic_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default_user',
            topic TEXT NOT NULL,
            mentions INTEGER DEFAULT 1,
            last_mentioned DATETIME DEFAULT (datetime('now')),
            UNIQUE(user_id, topic)
        )
    """,
    "session_summary": """
        CREATE TABLE IF NOT EXISTS session_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES session(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL DEFAULT 'default_user',
            pedagogical_facts TEXT DEFAULT '{}',
            text_summary TEXT DEFAULT '',
            turn_count INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT (datetime('now')),
            UNIQUE(session_id)
        )
    """,
    "pending_competency": """
        CREATE TABLE IF NOT EXISTS pending_competency (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default_user',
            proposed_name TEXT NOT NULL,
            proposed_domain TEXT DEFAULT '',
            parent_competency_id INTEGER REFERENCES competency(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """,
}

MEMORY_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_scs_session ON session_competency_score(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_scs_competency ON session_competency_score(competency_id)",
    "CREATE INDEX IF NOT EXISTS idx_me_competency ON method_effectiveness(competency_id)",
    "CREATE INDEX IF NOT EXISTS idx_uth_user ON user_topic_history(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_ss_session ON session_summary(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_pc_user ON pending_competency(user_id)",
]


def run_migrations(db_path: Optional[Path] = None) -> dict:
    """Applique les migrations V3 de manière idempotente.

    Retourne un dict avec les changements appliqués.
    En mode Postgres (DATABASE_URL definie), le schema est suppose deja applique
    (via schema_v3_postgres.sql) : on ne fait rien.
    """
    from apps.api.db.database import is_postgres
    if is_postgres():
        logger.info("Mode PostgreSQL : migrations SQLite ignorees (schema deja applique).")
        return {
            "tables_created": [],
            "columns_added": [],
            "indexes_created": [],
            "triggers_created": [],
        }

    from apps.api.config import DB_PATH
    path = db_path or DB_PATH

    changes = {
        "tables_created": [],
        "columns_added": [],
        "indexes_created": [],
        "triggers_created": [],
    }

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        existing_tables = _get_existing_tables(conn)
        existing_indexes = _get_existing_indexes(conn)
        existing_triggers = _get_existing_triggers(conn)

        # 1. Créer les nouvelles tables
        for table_name, create_sql in V3_TABLES.items():
            if table_name not in existing_tables:
                conn.execute(create_sql)
                changes["tables_created"].append(table_name)
                logger.info(f"Created table: {table_name}")

        # 1bis. Créer les tables mémoire (Phase 2 — Learner Model)
        for table_name, create_sql in MEMORY_TABLES.items():
            if table_name not in existing_tables:
                conn.execute(create_sql)
                changes["tables_created"].append(table_name)
                logger.info(f"Created memory table: {table_name}")

        # 2. Ajouter les nouvelles colonnes
        for table_name, columns in V3_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            existing_cols = _get_existing_columns(conn, table_name)
            for col_name, col_def in columns.items():
                if col_name not in existing_cols:
                    try:
                        conn.execute(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"
                        )
                        changes["columns_added"].append(f"{table_name}.{col_name}")
                        logger.info(f"Added column: {table_name}.{col_name}")
                    except sqlite3.OperationalError as e:
                        logger.warning(f"Could not add {table_name}.{col_name}: {e}")

        # 3. Créer les index
        for idx_sql in V3_INDEXES:
            # Extraire le nom de l'index
            idx_name = idx_sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
            if idx_name not in existing_indexes:
                try:
                    conn.execute(idx_sql)
                    changes["indexes_created"].append(idx_name)
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not create index {idx_name}: {e}")

        # 3bis. Créer les index mémoire (Phase 2)
        for idx_sql in MEMORY_INDEXES:
            idx_name = idx_sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
            if idx_name not in existing_indexes:
                try:
                    conn.execute(idx_sql)
                    changes["indexes_created"].append(idx_name)
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not create memory index {idx_name}: {e}")

        # 4. Créer les triggers
        for trigger_sql in V3_TRIGGERS:
            trigger_name = trigger_sql.split("IF NOT EXISTS")[1].split("\n")[0].strip()
            if trigger_name not in existing_triggers:
                try:
                    conn.execute(trigger_sql)
                    changes["triggers_created"].append(trigger_name)
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not create trigger {trigger_name}: {e}")

        # 5. Insérer un profil par défaut si absent (V1 compat)
        existing = conn.execute(
            "SELECT id FROM learner_profile WHERE user_id = 'default_user'"
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO learner_profile (user_id, domain, niveau_global) "
                "VALUES ('default_user', '', '')"
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    total = (
        len(changes["tables_created"])
        + len(changes["columns_added"])
        + len(changes["indexes_created"])
        + len(changes["triggers_created"])
    )
    if total > 0:
        logger.info(f"Migration V3 appliquée: {total} changements")
    else:
        logger.info("Base déjà à jour, aucune migration nécessaire")

    return changes


def get_schema_info(db_path: Optional[Path] = None) -> dict:
    """Retourne des infos sur l'état actuel de la base."""
    from apps.api.config import DB_PATH
    path = db_path or DB_PATH

    if not path.exists():
        return {"exists": False}

    conn = sqlite3.connect(str(path))
    try:
        tables = _get_existing_tables(conn)
        info = {"exists": True, "tables": sorted(tables)}
        for table in sorted(tables):
            cols = _get_existing_columns(conn, table)
            info[table] = sorted(cols)
        return info
    finally:
        conn.close()
