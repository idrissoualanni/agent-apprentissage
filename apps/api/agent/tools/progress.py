"""Outil de suivi de progression et répétition espacée (Leitner) — port V2 → V3."""

import json
from datetime import datetime, timedelta
from langchain.tools import tool

# Intervalles Leitner (en jours) par boîte
LEITNER_INTERVALS = {
    0: 1,
    1: 2,
    2: 5,
    3: 10,
    4: 21,
    5: 45,
}


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


@tool
def update_mastery_after_quiz(competency_id: int, is_correct: bool) -> str:
    """Met à jour la maîtrise d'une compétence après une tentative de quiz.

    Args:
        competency_id: ID de la compétence dans la base
        is_correct: True si la réponse est correcte, False sinon

    Returns:
        JSON string avec nouveau score, boîte Leitner, statut, prochaine révision
    """
    from apps.api.db import crud

    current = crud.get_mastery(competency_id)

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

    crud.upsert_mastery(
        competency_id, score, leitner_box, status,
        next_review_at=_next_review(leitner_box),
    )

    return json.dumps({
        "score": round(score, 2),
        "leitner_box": leitner_box,
        "status": status,
        "next_review": _next_review(leitner_box),
    }, ensure_ascii=False)


@tool
def update_mastery_after_feynman(competency_id: int, score: float) -> str:
    """Met à jour la maîtrise d'une compétence après une restitution Feynman.

    Args:
        competency_id: ID de la compétence dans la base
        score: Score de l'évaluation Feynman (0.0 à 1.0)

    Returns:
        JSON string avec nouveau score, boîte Leitner, statut, prochaine révision
    """
    from apps.api.db import crud

    current = crud.get_mastery(competency_id)

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
    crud.upsert_mastery(
        competency_id, score, leitner_box, status,
        next_review_at=_next_review(leitner_box),
    )

    return json.dumps({
        "score": round(score, 2),
        "leitner_box": leitner_box,
        "status": status,
        "next_review": _next_review(leitner_box),
    }, ensure_ascii=False)


@tool
def get_progress_summary(domain: str) -> str:
    """Retourne un résumé de progression pour un domaine donné.

    Args:
        domain: Domaine d'apprentissage (ex: "Mathématiques", "Python")

    Returns:
        JSON string avec total_competencies, average_score, acquired, learning, new, due_for_review, gaps
    """
    from apps.api.db import crud

    overview = crud.get_mastery_overview(domain)

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
    due = crud.get_due_for_review()

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


@tool
def get_revision_plan(domain: str = "") -> str:
    """Génère un plan de révision basé sur les compétences en retard (Leitner).

    Args:
        domain: Domaine d'apprentissage (optionnel, filtre si fourni)

    Returns:
        JSON string avec plan de révision ordonné par urgence
    """
    from apps.api.db import crud

    due = crud.get_due_for_review()
    if domain:
        due = [c for c in due if c.get("domain") == domain]
    if not due:
        return json.dumps({
            "plan": [],
            "message": "Aucune révision nécessaire aujourd'hui.",
        }, ensure_ascii=False)

    plan = [
        {
            "competency_id": c["id"],
            "nom": c["nom"],
            "score": c["score"],
            "leitner_box": c["leitner_box"],
            "next_review": c["next_review_at"],
        }
        for c in due[:5]
    ]
    return json.dumps({
        "plan": plan,
        "total_due": len(due),
        "message": f"{len(plan)} compétence(s) à réviser sur {len(due)} en retard.",
    }, ensure_ascii=False)
