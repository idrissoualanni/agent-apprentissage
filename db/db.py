"""Couche d'accès à la base SQLite — connexion, init, requêtes métier."""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

import config

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


@contextmanager
def get_connection(db_path: Optional[Path] = None):
    """Context manager pour une connexion SQLite avec WAL mode et foreign keys."""
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialise la base en appliquant le schéma SQL."""
    path = db_path or config.DB_PATH
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(path) as conn:
        conn.executescript(schema)
    # Insère un profil par défaut si absent
    with get_connection(path) as conn:
        existing = conn.execute("SELECT id FROM learner_profile WHERE id = 1").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO learner_profile (id, domain, niveau_global) VALUES (1, '', '')"
            )


# ─── Profil ───────────────────────────────────────────────────────────────

def get_profile(db_path: Optional[Path] = None) -> dict:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM learner_profile WHERE id = 1").fetchone()
        return dict(row) if row else {}


def update_profile(domain: str, niveau_global: str, db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE learner_profile SET domain = ?, niveau_global = ? WHERE id = 1",
            (domain, niveau_global),
        )


# ─── Compétences ──────────────────────────────────────────────────────────

def create_competency(domain: str, nom: str, parent_id: Optional[int] = None,
                      description: str = "", db_path: Optional[Path] = None) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO competency (domain, nom, parent_id, description) VALUES (?, ?, ?, ?)",
            (domain, nom, parent_id, description),
        )
        return cursor.lastrowid


def get_competencies(domain: str, db_path: Optional[Path] = None) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM competency WHERE domain = ? ORDER BY parent_id NULLS FIRST, nom",
            (domain,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_competency_tree(domain: str, db_path: Optional[Path] = None) -> list[dict]:
    """Retourne les compétences avec leur niveau de profondeur."""
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


# ─── Mastery ──────────────────────────────────────────────────────────────

def get_mastery(competency_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM mastery WHERE competency_id = ?", (competency_id,)
        ).fetchone()
        return dict(row) if row else None


def upsert_mastery(competency_id: int, score: float, leitner_box: int = 0,
                    status: str = "new", db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO mastery (competency_id, score, leitner_box, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(competency_id) DO UPDATE SET
                score = excluded.score,
                leitner_box = excluded.leitner_box,
                status = excluded.status,
                last_reviewed_at = datetime('now'),
                next_review_at = CASE
                    WHEN excluded.leitner_box > mastery.leitner_box
                    THEN datetime('now', '+' || (excluded.leitner_box * 2) || ' days')
                    ELSE next_review_at
                END
        """, (competency_id, score, leitner_box, status))


def get_mastery_overview(domain: str, db_path: Optional[Path] = None) -> list[dict]:
    """Vue d'ensemble : compétences + mastery pour un domaine."""
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
            ORDER BY c.parent_id NULLS FIRST, c.nom
        """, (domain,)).fetchall()
        return [dict(r) for r in rows]


def get_due_for_review(db_path: Optional[Path] = None) -> list[dict]:
    """Compétences dont next_review_at est dépassé (répétition espacée)."""
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


# ─── Documents ────────────────────────────────────────────────────────────

def create_document(filename: str, file_path: str, num_chunks: int = 0,
                    db_path: Optional[Path] = None) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO document (filename, file_path, num_chunks) VALUES (?, ?, ?)",
            (filename, file_path, num_chunks),
        )
        return cursor.lastrowid


def list_documents(db_path: Optional[Path] = None) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM document ORDER BY uploaded_at DESC").fetchall()
        return [dict(r) for r in rows]


# ─── Sessions & Messages ─────────────────────────────────────────────────

def create_session(thread_id: str, db_path: Optional[Path] = None) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO session (langgraph_thread_id) VALUES (?)", (thread_id,)
        )
        return cursor.lastrowid


def close_session(session_id: int, db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE session SET ended_at = datetime('now') WHERE id = ?", (session_id,)
        )


def add_message(session_id: int, role: str, content: str,
                method_used: Optional[str] = None, db_path: Optional[Path] = None) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO message (session_id, role, content, method_used) VALUES (?, ?, ?, ?)",
            (session_id, role, content, method_used),
        )
        return cursor.lastrowid


def get_session_messages(session_id: int, db_path: Optional[Path] = None) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM message WHERE session_id = ? ORDER BY created_at", (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Quiz ─────────────────────────────────────────────────────────────────

def record_quiz_attempt(competency_id: int, question: str, options: str,
                        user_answer: str, is_correct: bool,
                        session_id: Optional[int] = None,
                        db_path: Optional[Path] = None) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO quiz_attempt
               (competency_id, session_id, question, options, user_answer, is_correct)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (competency_id, session_id, question, options, user_answer, is_correct),
        )
        return cursor.lastrowid


# ─── Feynman ──────────────────────────────────────────────────────────────

def record_feynman_restitution(competency_id: int, user_explanation: str,
                               agent_evaluation: str, score: float,
                               gaps_identified: str,
                               session_id: Optional[int] = None,
                               db_path: Optional[Path] = None) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO feynman_restitution
               (competency_id, session_id, user_explanation, agent_evaluation, score, gaps_identified)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (competency_id, session_id, user_explanation, agent_evaluation, score, gaps_identified),
        )
        return cursor.lastrowid
