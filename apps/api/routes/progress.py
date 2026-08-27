"""Routes progress — progression, maîtrise, plan de révision."""

from fastapi import APIRouter
from typing import Optional

from apps.api.db import crud
from apps.api.agent.tools.progress import get_progress_summary, get_revision_plan
from apps.api.agent.memory import revision_planner
import apps.api.config as config

router = APIRouter(tags=["progress"])


@router.get("/overview")
def mastery_overview(domain: str = ""):
    """Vue d'ensemble de la maîtrise (toutes les compétences si domain vide)."""
    overview = crud.get_mastery_overview(domain=domain, db_path=config.DB_PATH)
    return {"overview": overview}


@router.get("/due")
def due_for_review():
    """Compétences dues pour révision (Leitner)."""
    due = crud.get_due_for_review(db_path=config.DB_PATH)
    return {"due": due, "count": len(due)}


@router.get("/revision-plan")
def revision_plan(domain: str = ""):
    """Plan de révision intelligent."""
    result = get_revision_plan.invoke({"domain": domain})
    import json
    return json.loads(result)


@router.get("/summary")
def progress_summary(domain: str = ""):
    """Résumé de progression."""
    result = get_progress_summary.invoke({"domain": domain})
    import json
    return json.loads(result)


# ─── Phase 6 : calendrier de revision (repetition espacee) ───────────────


@router.get("/revision/calendar")
def revision_calendar():
    """Calendrier de revision complet par competence (Phase 6)."""
    calendar = revision_planner.get_revision_calendar(db_path=config.DB_PATH)
    return {"calendar": calendar, "count": len(calendar)}


@router.get("/revision/due")
def revision_due(limit: int = 20):
    """Competences dont la revision est due maintenant (Phase 6)."""
    due = revision_planner.get_due_reviews(db_path=config.DB_PATH, limit=limit)
    return {"due": due, "count": len(due)}
