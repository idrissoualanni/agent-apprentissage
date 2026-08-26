"""Learner Model — base de connaissance utilisateur (Phase 2).

CRUD pour :
- score par competence ET par session (session_competency_score)
- efficacite des methodes par competence (method_effectiveness)
- sujets habituels de l'utilisateur (user_topic_history)
- resume compacte de session (session_summary)

Inspire par Duolingo Birdbrain (probabilite de reussite) et Squirrel AI
(granularite de competences). Utilise le meme pattern de connexion que crud.py.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from apps.api.db.crud import get_connection

logger = logging.getLogger(__name__)


# ─── Score par competence et par session ─────────────────────────────────


def update_session_score(
    session_id: int,
    competency_id: int,
    score: float,
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> None:
    """Upsert le score d'une competence pour une session donnee."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO session_competency_score (user_id, session_id, competency_id, score)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, competency_id)
            DO UPDATE SET score = excluded.score, updated_at = datetime('now')
            """,
            (user_id, session_id, competency_id, score),
        )


def get_session_score(
    session_id: int,
    competency_id: int,
    db_path: Optional[Path] = None,
) -> Optional[float]:
    """Retourne le score d'une competence pour une session, ou None."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT score FROM session_competency_score WHERE session_id = ? AND competency_id = ?",
            (session_id, competency_id),
        ).fetchone()
    return row["score"] if row else None


def update_p_success(
    session_id: int,
    competency_id: int,
    p_success: float,
    db_path: Optional[Path] = None,
) -> None:
    """Met a jour la probabilite de reussite estimee (inspiration Birdbrain)."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE session_competency_score SET p_success = ?, updated_at = datetime('now')
            WHERE session_id = ? AND competency_id = ?
            """,
            (p_success, session_id, competency_id),
        )


# ─── Efficacite des methodes ─────────────────────────────────────────────


def record_method_outcome(
    competency_id: int,
    method: str,
    success: bool,
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> None:
    """Enregistre le resultat d'une methode pour une competence.

    Incremente uses (et successes si succes), puis recalcule effectiveness.
    """
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO method_effectiveness (user_id, competency_id, method, uses, successes, effectiveness)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(competency_id, method)
            DO UPDATE SET
                uses = uses + 1,
                successes = successes + excluded.successes,
                effectiveness = CAST(successes + excluded.successes AS REAL) / (uses + 1),
                updated_at = datetime('now')
            """,
            (user_id, competency_id, method, 1 if success else 0, 1.0 if success else 0.0),
        )


def get_method_effectiveness(
    competency_id: int,
    db_path: Optional[Path] = None,
) -> dict:
    """Retourne {method: {uses, successes, effectiveness}} pour une competence."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT method, uses, successes, effectiveness FROM method_effectiveness WHERE competency_id = ?",
            (competency_id,),
        ).fetchall()
    return {
        r["method"]: {
            "uses": r["uses"],
            "successes": r["successes"],
            "effectiveness": r["effectiveness"],
        }
        for r in rows
    }


# ─── Sujets habituels ────────────────────────────────────────────────────


def bump_topic(
    user_id: str,
    topic: str,
    db_path: Optional[Path] = None,
) -> None:
    """Incremente le compteur de mentions d'un sujet (ou le cree)."""
    topic = topic.strip()
    if not topic:
        return
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_topic_history (user_id, topic, mentions)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, topic)
            DO UPDATE SET mentions = mentions + 1, last_mentioned = datetime('now')
            """,
            (user_id, topic),
        )


def get_top_topics(
    user_id: str,
    limit: int = 5,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Retourne les sujets les plus abordes par l'utilisateur."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT topic, mentions FROM user_topic_history WHERE user_id = ? "
            "ORDER BY mentions DESC, last_mentioned DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [{"topic": r["topic"], "mentions": r["mentions"]} for r in rows]


# ─── Resume de session ───────────────────────────────────────────────────


def upsert_session_summary(
    session_id: int,
    pedagogical_facts: dict,
    text_summary: str,
    turn_count: int,
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> None:
    """Upsert le resume compacte d'une session (faits + resume textuel)."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO session_summary (session_id, user_id, pedagogical_facts, text_summary, turn_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id)
            DO UPDATE SET
                pedagogical_facts = excluded.pedagogical_facts,
                text_summary = excluded.text_summary,
                turn_count = excluded.turn_count,
                updated_at = datetime('now')
            """,
            (session_id, user_id, json.dumps(pedagogical_facts, ensure_ascii=False), text_summary, turn_count),
        )


def get_session_summary(
    session_id: int,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """Retourne le resume d'une session, ou None."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT pedagogical_facts, text_summary, turn_count FROM session_summary WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    try:
        facts = json.loads(row["pedagogical_facts"])
    except (json.JSONDecodeError, TypeError):
        facts = {}
    return {
        "pedagogical_facts": facts,
        "text_summary": row["text_summary"],
        "turn_count": row["turn_count"],
    }


# ─── Competences dynamiques (en attente de validation) ───────────────────


def propose_competency(
    proposed_name: str,
    proposed_domain: str = "",
    parent_competency_id: Optional[int] = None,
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> int:
    """Cree une proposition de competence en attente de validation. Retourne son id."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO pending_competency (user_id, proposed_name, proposed_domain, parent_competency_id, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (user_id, proposed_name.strip(), proposed_domain.strip(), parent_competency_id),
        )
        return cur.lastrowid


def get_pending_competency(
    user_id: str = "default_user",
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """Retourne la derniere competence en attente pour l'utilisateur, ou None."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id, proposed_name, proposed_domain, parent_competency_id, status "
            "FROM pending_competency WHERE user_id = ? AND status = 'pending' "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "proposed_name": row["proposed_name"],
        "proposed_domain": row["proposed_domain"],
        "parent_competency_id": row["parent_competency_id"],
        "status": row["status"],
    }


def resolve_pending_competency(
    pending_id: int,
    status: str,
    db_path: Optional[Path] = None,
) -> None:
    """Marque une proposition comme 'approved' ou 'rejected'."""
    if status not in ("approved", "rejected"):
        raise ValueError("status doit etre 'approved' ou 'rejected'")
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_competency SET status = ? WHERE id = ?",
            (status, pending_id),
        )


def find_similar_competency(
    proposed_name: str,
    domain: str,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """Cherche une competence existante au nom proche (evite les doublons).

    Retourne la competence si le nom (normalise) est deja present dans le domaine.
    """
    normalized = proposed_name.strip().lower()
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, nom, domain FROM competency WHERE domain = ?", (domain,)
        ).fetchall()
    for r in rows:
        if r["nom"].strip().lower() == normalized:
            return {"id": r["id"], "nom": r["nom"], "domain": r["domain"]}
    return None


# ─── Contexte agrege pour le context_builder ─────────────────────────────


def get_learner_context(
    user_id: str,
    session_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> dict:
    """Construit le contexte apprenant injecte dans l'etat.

    Agrege : niveau par competence, scores de la session, meilleures methodes,
    sujets habituels, et resume de session.
    """
    with get_connection(db_path) as conn:
        # Niveau global par competence (mastery). NB: mastery n'a pas de user_id.
        mastery_rows = conn.execute(
            """
            SELECT c.id, c.nom, c.domain, m.score AS mastery_score, m.leitner_box
            FROM competency c
            LEFT JOIN mastery m ON m.competency_id = c.id
            """
        ).fetchall()

        competencies = [
            {
                "id": r["id"],
                "nom": r["nom"],
                "domain": r["domain"],
                "mastery_score": r["mastery_score"],
                "leitner_box": r["leitner_box"],
            }
            for r in mastery_rows
        ]

        # Scores de la session en cours
        session_scores = {}
        if session_id is not None:
            score_rows = conn.execute(
                "SELECT competency_id, score, p_success FROM session_competency_score WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            session_scores = {
                r["competency_id"]: {"score": r["score"], "p_success": r["p_success"]}
                for r in score_rows
            }

        # Resume de session
        summary_row = None
        if session_id is not None:
            summary_row = conn.execute(
                "SELECT pedagogical_facts, text_summary, turn_count FROM session_summary WHERE session_id = ?",
                (session_id,),
            ).fetchone()

    # Meilleures methodes par competence (depuis method_effectiveness)
    method_eff = {}
    for comp in competencies:
        eff = get_method_effectiveness(comp["id"], db_path=db_path)
        if eff:
            best = max(eff.items(), key=lambda kv: kv[1]["effectiveness"])
            method_eff[comp["id"]] = best[0]

    session_summary = None
    if summary_row:
        try:
            facts = json.loads(summary_row["pedagogical_facts"])
        except (json.JSONDecodeError, TypeError):
            facts = {}
        session_summary = {
            "pedagogical_facts": facts,
            "text_summary": summary_row["text_summary"],
            "turn_count": summary_row["turn_count"],
        }

    return {
        "competencies": competencies,
        "session_scores": session_scores,
        "best_method_by_competency": method_eff,
        "top_topics": get_top_topics(user_id, limit=5, db_path=db_path),
        "session_summary": session_summary,
    }
