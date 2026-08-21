"""Outil de suivi de progression et repetition espacée (Leitner)."""

import json
from datetime import datetime, timedelta
from langchain.tools import tool

from db import db
import config

# Intervalles Leitner (en jours) par boite
LEITNER_INTERVALS = {
    0: 1,    # nouvelle competence -> revision le lendemain
    1: 2,    # 1ere reussite -> 2 jours
    2: 5,    # 2eme -> 5 jours
    3: 10,   # 3eme -> 10 jours
    4: 21,   # 4eme -> 3 semaines
    5: 45,   # 5eme -> consideree acquise
}


@tool
def update_mastery_after_quiz(competency_id: int, is_correct: bool) -> str:
    """Met a jour la maitrise d'une competence apres une tentative de quiz.

    Args:
        competency_id: ID de la competence dans la base
        is_correct: True si la reponse est correcte, False sinon

    Returns:
        JSON string avec nouveau score, boite Leitner, statut, prochaine revision
    """
    current = db.get_mastery(competency_id, config.DB_PATH)

    if current is None:
        score = 0.5 if is_correct else 0.2
        leitner_box = 1 if is_correct else 0
        status = "learning" if is_correct else "new"
    else:
        score = current["score"]
        leitner_box = current["leitner_box"]
        delta = 0.15 if is_correct else -0.1
        score = max(0.0, min(1.0, score + delta))

        if is_correct:
            leitner_box = min(5, leitner_box + 1)
        else:
            leitner_box = max(0, leitner_box - 1)

        status = _compute_status(score, leitner_box)

    db.upsert_mastery(competency_id, score, leitner_box, status,
                       next_review_at=_next_review(leitner_box),
                       db_path=config.DB_PATH)

    return json.dumps({
        "score": round(score, 2),
        "leitner_box": leitner_box,
        "status": status,
        "next_review": _next_review(leitner_box),
    }, ensure_ascii=False)


@tool
def update_mastery_after_feynman(competency_id: int, score: float) -> str:
    """Met a jour la maitrise d'une competence apres une restitution Feynman.

    Args:
        competency_id: ID de la competence dans la base
        score: Score de l'evaluation Feynman (0.0 a 1.0)

    Returns:
        JSON string avec nouveau score, boite Leitner, statut, prochaine revision
    """
    current = db.get_mastery(competency_id, config.DB_PATH)

    if current is None:
        leitner_box = 2 if score >= 0.7 else (1 if score >= 0.4 else 0)
    else:
        old_score = current["score"]
        score = old_score * 0.3 + score * 0.7
        leitner_box = current["leitner_box"]

        if score >= 0.8:
            leitner_box = min(5, leitner_box + 1)
        elif score < 0.4:
            leitner_box = max(0, leitner_box - 1)

    status = _compute_status(score, leitner_box)
    db.upsert_mastery(competency_id, score, leitner_box, status,
                       next_review_at=_next_review(leitner_box),
                       db_path=config.DB_PATH)

    return json.dumps({
        "score": round(score, 2),
        "leitner_box": leitner_box,
        "status": status,
        "next_review": _next_review(leitner_box),
    }, ensure_ascii=False)


@tool
def get_progress_summary(domain: str) -> str:
    """Retourne un resume de progression pour un domaine donne.

    Args:
        domain: Domaine d'apprentissage (ex: "Mathematiques", "Python")

    Returns:
        JSON string avec total_competencies, average_score, acquired, learning, new, due_for_review, gaps
    """
    overview = db.get_mastery_overview(domain, config.DB_PATH)

    if not overview:
        return json.dumps({
            "total_competencies": 0,
            "average_score": 0,
            "acquired": 0,
            "learning": 0,
            "new": 0,
            "due_for_review": 0,
            "gaps": [],
        })

    scores = [c["score"] for c in overview]
    due = db.get_due_for_review(config.DB_PATH)

    return json.dumps({
        "total_competencies": len(overview),
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "acquired": sum(1 for c in overview if c["status"] == "acquired"),
        "learning": sum(1 for c in overview if c["status"] == "learning"),
        "new": sum(1 for c in overview if c["status"] == "new"),
        "due_for_review": len(due),
        "gaps": [
            {"id": c["id"], "nom": c["nom"], "score": c["score"]}
            for c in overview if c["score"] < 0.4
        ],
    }, ensure_ascii=False)


# ─── Helpers internes (pas des tools) ─────────────────────────────────────

def _compute_status(score: float, leitner_box: int) -> str:
    if score >= 0.8 and leitner_box >= 3:
        return "acquired"
    elif score >= 0.4:
        return "learning"
    elif leitner_box > 0:
        return "review"
    return "new"


def _next_review(leitner_box: int) -> str:
    days = LEITNER_INTERVALS.get(leitner_box, 1)
    return (datetime.now() + timedelta(days=days)).isoformat()
