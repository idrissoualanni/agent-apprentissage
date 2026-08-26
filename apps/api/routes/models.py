"""Routes models — gestion du catalogue de modèles LLM."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from apps.api.services.model_manager import ModelManager, OPERATION_PRESETS
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
    return {"catalog": mm.list_available()}


@router.get("/active")
async def get_active():
    """Retourne les modèles actifs (par opération)."""
    return {
        "active": {
            op: preset.get("model_name")
            for op, preset in OPERATION_PRESETS.items()
        }
    }


@router.post("/select")
async def select_model(operation: str, model_id: str):
    """Sélectionne un modèle pour une opération (en mémoire jusqu'au restart)."""
    mm = _get_manager()
    if mm.get_config(model_id) is None:
        return {"ok": False, "error": f"Modèle inconnu : {model_id}"}
    if operation not in OPERATION_PRESETS:
        return {"ok": False, "error": f"Opération inconnue : {operation}"}
    OPERATION_PRESETS[operation]["model_name"] = model_id
    return {"ok": True}


@router.get("/status")
async def model_status():
    """Statut des modèles (connectivité Ollama)."""
    from apps.api.llm.cloud_providers import list_local_models
    try:
        local = list_local_models()
        return {"local_models": local, "status": "connected"}
    except Exception as e:
        return {"local_models": [], "status": "error", "error": str(e)}
