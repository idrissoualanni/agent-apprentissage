"""Routes models — gestion du catalogue de modèles LLM."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from apps.api.services.model_manager import ModelManager
from apps.api.db import crud
import apps.api.config as config

router = APIRouter(tags=["models"])

_manager = None


def _get_manager() -> ModelManager:
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager


@router.get("/catalog")
async def list_catalog():
    """Liste le catalogue complet de modèles."""
    mm = _get_manager()
    return {"catalog": mm.list_catalog()}


@router.get("/active")
async def get_active():
    """Retourne les modèles actifs (par opération)."""
    mm = _get_manager()
    return {"active": mm.get_active_models()}


@router.post("/select")
async def select_model(operation: str, model_id: str):
    """Sélectionne un modèle pour une opération."""
    mm = _get_manager()
    success = mm.select_model(operation, model_id, db_path=config.DB_PATH)
    return {"ok": success}


@router.get("/status")
async def model_status():
    """Statut des modèles (connectivité Ollama)."""
    from apps.api.llm.cloud_providers import list_local_models
    try:
        local = list_local_models()
        return {"local_models": local, "status": "connected"}
    except Exception as e:
        return {"local_models": [], "status": "error", "error": str(e)}
