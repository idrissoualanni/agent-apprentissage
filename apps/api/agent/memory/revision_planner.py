"""Revision Planner (Phase 6) — repetition espacee basee sur Leitner.

Calcule les dates de revision par competence et expose un calendrier de
revision pour la page /revision. Inspire par Anki/SuperMemo (intervalles
croissants) et la methode Leitner (boites 0-5).
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from apps.api.db.crud import get_connection

logger = logging.getLogger(__name__)

# Intervalles de revision (jours) par boite de Leitner.
LEITNER_INTERVALS_DAYS = {
    0: 1,
    1: 2,
    2: 5,
    3: 9,
    4: 14,
    5: 30,
}


def compute_next_review(leitner_box: int, from_dt: Optional[datetime] = None) -> datetime:
    """Calcule la prochaine date de revision depuis une boite de Leitner."""
    base = from_dt or datetime.now()
    days = LEITNER_INTERVALS_DAYS.get(leitner_box, 1)
    return base + timedelta(days=days)


def schedule_review(
    competency_id: int,
    leitner_box: int,
    db_path: Optional[Path] = None,
) -> str:
    """Planifie la prochaine revision pour une competence. Retourne la date ISO."""
    next_dt = compute_next_review(leitner_box)
    next_iso = next_dt.strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE mastery SET next_review_at = ?, last_reviewed_at = datetime('now') "
            "WHERE competency_id = ?",
            (next_iso, competency_id),
        )
    return next_iso


def get_due_reviews(
    db_path: Optional[Path] = None,
    limit: int = 20,
) -> list[dict]:
    """Retourne les competences dont la revision est due (next_review_at <= now)."""
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.nom, c.domain, m.score, m.leitner_box, m.next_review_at, m.status
            FROM mastery m
            JOIN competency c ON c.id = m.competency_id
            WHERE m.next_review_at IS NOT NULL AND m.next_review_at <= ?
            ORDER BY m.next_review_at ASC
            LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
    return [
        {
            "competency_id": r["id"],
            "nom": r["nom"],
            "domain": r["domain"],
            "score": r["score"],
            "leitner_box": r["leitner_box"],
            "next_review_at": r["next_review_at"],
            "status": r["status"],
        }
        for r in rows
    ]


def get_revision_calendar(
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Retourne le calendrier de revision complet (toutes competences avec une date)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.nom, c.domain, m.score, m.leitner_box,
                   m.next_review_at, m.last_reviewed_at, m.status
            FROM mastery m
            JOIN competency c ON c.id = m.competency_id
            WHERE m.next_review_at IS NOT NULL
            ORDER BY m.next_review_at ASC
            """
        ).fetchall()
    return [
        {
            "competency_id": r["id"],
            "nom": r["nom"],
            "domain": r["domain"],
            "score": r["score"],
            "leitner_box": r["leitner_box"],
            "next_review_at": r["next_review_at"],
            "last_reviewed_at": r["last_reviewed_at"],
            "status": r["status"],
        }
        for r in rows
    ]
