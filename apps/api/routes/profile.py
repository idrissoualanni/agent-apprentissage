"""Routes profile — gestion du profil apprenant."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Literal, Optional

from apps.api.db import crud
import apps.api.config as config

router = APIRouter(tags=["profile"])


class ProfileUpdate(BaseModel):
    domain: Optional[str] = Field(None, min_length=1, max_length=200)
    # Literal : seul l'un de ces trois niveaux exacts est accepté —
    # en miroir du <select> du frontend (app/profile/page.tsx).
    niveau_global: Optional[Literal["debutant", "intermediaire", "avance"]] = None
    # Correctif : ces deux champs étaient envoyés par le frontend (page Profil)
    # mais ignorés silencieusement par Pydantic → jamais sauvegardés en DB.
    learning_context: Optional[str] = Field(None, max_length=4000)
    goals: Optional[str] = Field(None, max_length=4000)


@router.get("")
def get_profile():
    """Récupère le profil apprenant."""
    profile = crud.get_profile(db_path=config.DB_PATH)
    return profile


@router.put("")
def update_profile(req: ProfileUpdate):
    """Met à jour le profil apprenant."""
    crud.update_profile(
        domain=req.domain or "",
        niveau_global=req.niveau_global or "",
        learning_context=req.learning_context or "",
        goals=req.goals or "",
        db_path=config.DB_PATH,
    )
    return {"ok": True}


@router.get("/tree")
def get_competency_tree(domain: str = ""):
    """Récupère l'arbre des compétences pour un domaine."""
    tree = crud.get_competency_tree(domain, db_path=config.DB_PATH)
    return {"tree": tree}


@router.get("/competencies")
def list_competencies(domain: str = ""):
    """Liste les compétences d'un domaine."""
    comps = crud.get_competencies(domain, db_path=config.DB_PATH)
    return {"competencies": comps}
