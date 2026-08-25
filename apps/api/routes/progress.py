"""Routes progress — progression, maîtrise, plan de révision."""

from fastapi import APIRouter
from typing import Optional

from apps.api.db import crud
from apps.api.agent.tools.progress import get_progress_summary, get_revision_plan
import apps.api.config as config

router = APIRouter(tags=["progress"])


@router.get("/overview")
async def mastery_overview():
    """Vue d'ensemble de la maîtrise (toutes les compétences)."""
    overview = crud.get_mastery_overview(db_path=config.DB_PATH)
    return {"overview": overview}


@router.get("/due")
async def due_for_review():
    """Compétences dues pour révision (Leitner)."""
    due = crud.get_due_for_review(db_path=config.DB_PATH)
    return {"due": due, "count": len(due)}


@router.get("/revision-plan")
async def revision_plan(domain: str = ""):
    """Plan de révision intelligent."""
    result = get_revision_plan.invoke({"domain": domain})
    import json
    return json.loads(result)


@router.get("/summary")
async def progress_summary(domain: str = ""):
    """Résumé de progression."""
    result = get_progress_summary.invoke({"domain": domain})
    import json
    return json.loads(result)
