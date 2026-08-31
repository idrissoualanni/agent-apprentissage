"""Routes sessions — CRUD des sessions de conversation."""

import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from apps.api.db import crud
import apps.api.config as config
from apps.api.services.checkpoint import get_thread_id_from_session, clear_checkpoint

router = APIRouter(tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = Field("Nouvelle session", min_length=1, max_length=120)
    user_id: str = Field("default_user", min_length=1, max_length=64)


class SessionUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


@router.get("")
def list_sessions(user_id: str = "default_user"):
    """Liste les sessions de l'utilisateur."""
    sessions = crud.list_sessions(user_id, db_path=config.DB_PATH)
    return {"sessions": sessions}


@router.post("")
def create_session(req: SessionCreate):
    """Crée une nouvelle session."""
    thread_id = str(uuid.uuid4())
    session_id = crud.create_session(
        thread_id=thread_id,
        title=req.title,
        user_id=req.user_id,
        db_path=config.DB_PATH,
    )
    return {"id": session_id, "thread_id": thread_id, "title": req.title}


@router.get("/{session_id}")
def get_session(session_id: int):
    """Récupère une session par ID."""
    session = crud.get_session(session_id, db_path=config.DB_PATH)
    if not session:
        raise HTTPException(404, "Session non trouvée")
    return session


@router.put("/{session_id}")
def update_session(session_id: int, req: SessionUpdate):
    """Met à jour le titre d'une session."""
    if req.title:
        crud.update_session_title(session_id, req.title, db_path=config.DB_PATH)
    return {"ok": True}


@router.delete("/{session_id}")
def delete_session(session_id: int):
    """Supprime une session et son checkpoint."""
    thread_id = get_thread_id_from_session(session_id)
    if thread_id:
        clear_checkpoint(thread_id)
    crud.delete_session(session_id, db_path=config.DB_PATH)
    return {"ok": True}


@router.get("/{session_id}/messages")
def get_messages(session_id: int):
    """Récupère les messages d'une session."""
    messages = crud.get_session_messages(session_id, db_path=config.DB_PATH)
    return {"messages": messages}
