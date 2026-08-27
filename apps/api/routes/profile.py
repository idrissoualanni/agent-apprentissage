"""Routes profile — gestion du profil apprenant."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from apps.api.db import crud
import apps.api.config as config

router = APIRouter(tags=["profile"])


class ProfileUpdate(BaseModel):
    domain: Optional[str] = None
    niveau_global: Optional[str] = None


@router.get("")
def get_profile():
    """Récupère le profil apprenant."""
    profile = crud.get_profile(db_path=config.DB_PATH)
    return profile


@router.put("")
def update_profile(req: ProfileUpdate):
    """Met à jour le profil apprenant."""
    crud.update_profile(
        domain=req.domain,
        niveau_global=req.niveau_global,
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
