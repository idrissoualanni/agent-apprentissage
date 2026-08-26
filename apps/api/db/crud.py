"""CRUD V3 — opérations SQLite avec support async + multi-user."""

import sqlite3
import json
import hashlib
from pathlib import Path
from contextlib import contextmanager
from typing import Optional
from datetime import datetime, timedelta

import logging

logger = logging.getLogger(__name__)


@contextmanager
def get_connection(db_path: Optional[Path] = None):
    """Context manager pour une connexion DB (SQLite dev ou Postgres Neon prod).

    Delegue a apps.api.db.database.get_db_connection qui choisit le backend
    selon la presence de DATABASE_URL dans l'environnement.
    """
    from apps.api.db.database import get_db_connection
    with get_db_connection(db_path) as conn:
        yield conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialise la base avec le schéma V3 complet."""
    from apps.api.config import DB_PATH
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).resolve().parent / "schema_v3.sql"
    if schema_path.exists():
        schema = schema_path.read_text(encoding="utf-8")
        with get_connection(path) as conn:
            conn.executescript(schema)
    else:
        # Fallback: appliquer les migrations
        from apps.api.db.migrations import run_migrations
        run_migrations(path)

    # Insérer un profil par défaut si absent
    with get_connection(path) as conn:
        existing = conn.execute(
            "SELECT id FROM learner_profile WHERE user_id = 'default_user'"
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO learner_profile (user_id, domain, niveau_global) "
                "VALUES ('default_user', '', '')"
            )


# ═══════════════════════════════════════════════════════════════════════════
# PROFIL
# ═══════════════════════════════════════════════════════════════════════════

def get_profile(user_id: str = "default_user", db_path: Optional[Path] = None) -> dict:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM learner_profile WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else {}


def update_profile(
    domain: str = "",
    niveau_global: str = "",
    learning_context: str = "",
    goals: str = "",
    mastered_topics: str = "",
    learning_topics: str = "",
    gap_topics: str = "",
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute("""
            UPDATE learner_profile SET
                domain = COALESCE(NULLIF(?, ''), domain),
                niveau_global = COALESCE(NULLIF(?, ''), niveau_global),
                learning_context = COALESCE(NULLIF(?, ''), learning_context),
                goals = COALESCE(NULLIF(?, ''), goals),
                mastered_topics = COALESCE(NULLIF(?, ''), mastered_topics),
                learning_topics = COALESCE(NULLIF(?, ''), learning_topics),
                gap_topics = COALESCE(NULLIF(?, ''), gap_topics),
                updated_at = datetime('now')
            WHERE user_id = ?
        """, (domain, niveau_global, learning_context, goals,
              mastered_topics, learning_topics, gap_topics, user_id))


# ═══════════════════════════════════════════════════════════════════════════
# COMPÉTENCES
# ═══════════════════════════════════════════════════════════════════════════

def create_competency(
    domain: str, nom: str, parent_id: Optional[int] = None,
    description: str = "", db_path: Optional[Path] = None,
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO competency (domain, nom, parent_id, description) "
            "VALUES (?, ?, ?, ?)",
            (domain, nom, parent_id, description),
        )
        return cursor.lastrowid


def get_competencies(domain: str, db_path: Optional[Path] = None) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM competency WHERE domain = ? "
            "ORDER BY parent_id IS NULL DESC, parent_id, nom",
            (domain,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_competency_tree(domain: str, db_path: Optional[Path] = None) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            WITH RECURSIVE tree(id, nom, parent_id, depth, path) AS (
                SELECT id, nom, parent_id, 0, CAST(id AS TEXT)
                FROM competency WHERE domain = ? AND parent_id IS NULL
                UNION ALL
                SELECT c.id, c.nom, c.parent_id, t.depth + 1, t.path || '/' || c.id
                FROM competency c JOIN tree t ON c.parent_id = t.id
            )
            SELECT * FROM tree ORDER BY path
        """, (domain,)).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# MASTERY (Leitner)
# ═══════════════════════════════════════════════════════════════════════════

def get_mastery(competency_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM mastery WHERE competency_id = ?", (competency_id,)
        ).fetchone()
        return dict(row) if row else None


def upsert_mastery(
    competency_id: int, score: float, leitner_box: int = 0,
    status: str = "new", next_review_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO mastery (competency_id, score, leitner_box, status, next_review_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(competency_id) DO UPDATE SET
                score = excluded.score,
                leitner_box = excluded.leitner_box,
                status = excluded.status,
                last_reviewed_at = datetime('now'),
                next_review_at = excluded.next_review_at
        """, (competency_id, score, leitner_box, status, next_review_at))


def get_mastery_overview(domain: str, db_path: Optional[Path] = None) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT c.id, c.nom, c.parent_id,
                   COALESCE(m.score, 0) as score,
                   COALESCE(m.status, 'new') as status,
                   COALESCE(m.leitner_box, 0) as leitner_box,
                   m.next_review_at
            FROM competency c
            LEFT JOIN mastery m ON m.competency_id = c.id
            WHERE c.domain = ?
            ORDER BY c.parent_id IS NULL DESC, c.parent_id, c.nom
        """, (domain,)).fetchall()
        return [dict(r) for r in rows]


def get_due_for_review(db_path: Optional[Path] = None) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT c.id, c.nom, c.domain, m.score, m.leitner_box, m.next_review_at
            FROM mastery m
            JOIN competency c ON c.id = m.competency_id
            WHERE m.next_review_at IS NOT NULL
              AND m.next_review_at <= datetime('now')
            ORDER BY m.next_review_at
        """).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════

def create_document(
    filename: str, file_path: str, num_chunks: int = 0,
    db_path: Optional[Path] = None,
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO document (filename, file_path, num_chunks) VALUES (?, ?, ?)",
            (filename, file_path, num_chunks),
        )
        return cursor.lastrowid


def list_documents(db_path: Optional[Path] = None) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM document ORDER BY uploaded_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# SESSIONS & MESSAGES
# ═══════════════════════════════════════════════════════════════════════════

def create_session(
    thread_id: str, user_id: str = "default_user",
    title: str = "", db_path: Optional[Path] = None,
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO session (langgraph_thread_id, user_id, title) "
            "VALUES (?, ?, ?)",
            (thread_id, user_id, title),
        )
        return cursor.lastrowid


def close_session(session_id: int, db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE session SET ended_at = datetime('now') WHERE id = ?",
            (session_id,),
        )


def add_message(
    session_id: int, role: str, content: str,
    method_used: Optional[str] = None,
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO message (session_id, role, content, method_used, user_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, method_used, user_id),
        )
        return cursor.lastrowid


def get_session_messages(
    session_id: int, db_path: Optional[Path] = None,
) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM message WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_sessions(
    user_id: str = "default_user", db_path: Optional[Path] = None,
) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM session WHERE user_id = ? ORDER BY started_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_session(session_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM session WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None


def delete_session(session_id: int, db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM session WHERE id = ?", (session_id,))


def update_session_title(
    session_id: int, title: str, db_path: Optional[Path] = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE session SET title = ? WHERE id = ?", (title, session_id)
        )


# ═══════════════════════════════════════════════════════════════════════════
# QUIZ
# ═══════════════════════════════════════════════════════════════════════════

def record_quiz_attempt(
    competency_id: int, question: str, options: str,
    user_answer: str, is_correct: bool,
    session_id: Optional[int] = None,
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO quiz_attempt
               (competency_id, session_id, user_id, question, options, user_answer, is_correct)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (competency_id, session_id, user_id, question, options, user_answer, is_correct),
        )
        return cursor.lastrowid


# ═══════════════════════════════════════════════════════════════════════════
# FEYNMAN
# ═══════════════════════════════════════════════════════════════════════════

def record_feynman_restitution(
    competency_id: int, user_explanation: str,
    agent_evaluation: str, score: float,
    gaps_identified: str,
    session_id: Optional[int] = None,
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO feynman_restitution
               (competency_id, session_id, user_id, user_explanation,
                agent_evaluation, score, gaps_identified)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (competency_id, session_id, user_id,
             user_explanation, agent_evaluation, score, gaps_identified),
        )
        return cursor.lastrowid


# ═══════════════════════════════════════════════════════════════════════════
# ARTIFACTS
# ═══════════════════════════════════════════════════════════════════════════

def create_artifact(
    user_id: str = "default_user",
    session_id: Optional[int] = None,
    type: str = "schema",
    title: str = "",
    content: dict | str = "",
    format: str = "json",
    db_path: Optional[Path] = None,
) -> int:
    content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO artifact (user_id, session_id, type, title, content, format)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, session_id, type, title, content_str, format),
        )
        return cursor.lastrowid


def list_artifacts(
    user_id: str = "default_user",
    session_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    with get_connection(db_path) as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM artifact WHERE user_id = ? AND session_id = ? "
                "ORDER BY created_at DESC",
                (user_id, session_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM artifact WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_artifact(artifact_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM artifact WHERE id = ?", (artifact_id,)
        ).fetchone()
        return dict(row) if row else None


def delete_artifact(artifact_id: int, db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM artifact WHERE id = ?", (artifact_id,))


# ═══════════════════════════════════════════════════════════════════════════
# TOOL USAGE
# ═══════════════════════════════════════════════════════════════════════════

def log_tool_usage(
    tool_name: str,
    user_id: str = "default_user",
    session_id: Optional[int] = None,
    input_summary: str = "",
    output_summary: str = "",
    duration_ms: int = 0,
    success: bool = True,
    db_path: Optional[Path] = None,
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO tool_usage
               (user_id, session_id, tool_name, input_summary, output_summary,
                duration_ms, success)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, session_id, tool_name, input_summary, output_summary,
             duration_ms, success),
        )
        return cursor.lastrowid


def get_tool_usage(
    user_id: str = "default_user",
    session_id: Optional[int] = None,
    limit: int = 50,
    db_path: Optional[Path] = None,
) -> list[dict]:
    with get_connection(db_path) as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM tool_usage WHERE user_id = ? AND session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tool_usage WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# MODEL CONFIG
# ═══════════════════════════════════════════════════════════════════════════

def upsert_model_config(
    model_name: str,
    display_name: str = "",
    provider: str = "ollama_local",
    default_temperature: float = 0.3,
    format_mode: str = "json_or_markdown",
    max_tokens: int = 2048,
    is_active: bool = True,
    db_path: Optional[Path] = None,
) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute("""
            INSERT INTO model_config
                (model_name, display_name, provider, default_temperature,
                 format_mode, max_tokens, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_name) DO UPDATE SET
                display_name = excluded.display_name,
                provider = excluded.provider,
                default_temperature = excluded.default_temperature,
                format_mode = excluded.format_mode,
                max_tokens = excluded.max_tokens,
                is_active = excluded.is_active
        """, (model_name, display_name, provider, default_temperature,
              format_mode, max_tokens, is_active))
        return cursor.lastrowid


def list_model_configs(
    active_only: bool = False, db_path: Optional[Path] = None,
) -> list[dict]:
    with get_connection(db_path) as conn:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM model_config WHERE is_active = 1 "
                "ORDER BY model_name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM model_config ORDER BY model_name"
            ).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# WEB SEARCH CACHE
# ═══════════════════════════════════════════════════════════════════════════

def _hash_query(query: str, provider: str) -> str:
    return hashlib.sha256(f"{query}:{provider}".encode()).hexdigest()[:32]


def get_web_search_cache(
    query: str, provider: str = "ddgs",
    ttl_hours: int = 24,
    db_path: Optional[Path] = None,
) -> Optional[list]:
    query_hash = _hash_query(query, provider)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT results, fetched_at FROM web_search_cache WHERE query_hash = ?",
            (query_hash,),
        ).fetchone()
        if row:
            fetched_at = datetime.fromisoformat(row["fetched_at"])
            if datetime.now() - fetched_at < timedelta(hours=ttl_hours):
                return json.loads(row["results"])
        return None


def set_web_search_cache(
    query: str, provider: str, results: list,
    db_path: Optional[Path] = None,
) -> None:
    query_hash = _hash_query(query, provider)
    results_json = json.dumps(results, ensure_ascii=False)
    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO web_search_cache (query_hash, query, provider, results)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(query_hash) DO UPDATE SET
                results = excluded.results,
                fetched_at = datetime('now')
        """, (query_hash, query, provider, results_json))
