"""Routes chat — SSE streaming + HITL confirmation."""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from apps.api.services import agent_service
from apps.api.services.streaming import stream_tokens, stream_json_response
from apps.api.services.checkpoint import get_thread_id_from_session
from apps.api.db import crud
import apps.api.config as config

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[int] = None
    thread_id: Optional[str] = None
    user_id: str = "default_user"
    streaming: bool = False
    model_override: Optional[str] = None


class ConfirmationRequest(BaseModel):
    session_id: Optional[int] = None
    thread_id: Optional[str] = None
    user_id: str = "default_user"
    accepted: bool


@router.post("")
async def chat(req: ChatRequest):
    """Point d'entrée principal — envoie une question à l'agent.

    Accepte session_id (frontend) OU thread_id (direct).
    Retourne SSE si streaming=True, JSON sinon.
    """
    if not req.question.strip():
        raise HTTPException(400, "La question ne peut pas être vide")

    # Résoudre le thread_id depuis session_id si nécessaire
    thread_id = req.thread_id
    if not thread_id and req.session_id:
        thread_id = get_thread_id_from_session(req.session_id)
        if not thread_id:
            raise HTTPException(404, "Session introuvable ou sans thread_id")

    if req.streaming:
        token_gen = agent_service.run_agent_streaming(
            question=req.question,
            thread_id=thread_id,
            user_id=req.user_id,
            model_override=req.model_override,
        )
        return StreamingResponse(
            stream_tokens(token_gen),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = agent_service.run_agent(
            question=req.question,
            thread_id=thread_id,
            user_id=req.user_id,
            model_override=req.model_override,
        )

        # Sauvegarder les messages en DB si session_id fourni
        if req.session_id:
            try:
                crud.add_message(
                    session_id=req.session_id,
                    role="user",
                    content=req.question,
                    user_id=req.user_id,
                    db_path=config.DB_PATH,
                )
                method = result.get("method", "")
                crud.add_message(
                    session_id=req.session_id,
                    role="assistant",
                    content=result.get("answer", ""),
                    method_used=method if method and method != "error" else None,
                    user_id=req.user_id,
                    db_path=config.DB_PATH,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to save messages: {e}")

        # Construire la réponse avec message_id pour le frontend
        response = {
            "message_id": result.get("message_id"),
            "answer": result.get("answer", ""),
            "method": result.get("method"),
            "pending_confirmation": result.get("pending_confirmation", False),
            "confirmation_type": result.get("confirmation_type"),
            "confirmation_prompt": result.get("confirmation_prompt"),
            "artifacts": result.get("artifacts", []),
            "tool_transparency": result.get("tool_transparency", []),
            "thread_id": result.get("thread_id"),
        }
        return json.dumps(response, ensure_ascii=False)


@router.post("/confirm")
async def confirm_action(req: ConfirmationRequest):
    """Gère la réponse HITL (confirmation utilisateur)."""
    thread_id = req.thread_id
    if not thread_id and req.session_id:
        thread_id = get_thread_id_from_session(req.session_id)
        if not thread_id:
            raise HTTPException(404, "Session introuvable")

    result = agent_service.run_agent(
        question="",
        thread_id=thread_id,
        user_id=req.user_id,
        user_confirmed=req.accepted,
    )

    # Sauvegarder le message si session_id
    if req.session_id:
        try:
            crud.add_message(
                session_id=req.session_id,
                role="assistant",
                content=result.get("answer", ""),
                method_used=result.get("method"),
                user_id=req.user_id,
                db_path=config.DB_PATH,
            )
        except Exception:
            pass

    return {
        "message_id": result.get("message_id"),
        "answer": result.get("answer", ""),
        "method": result.get("method"),
        "pending_confirmation": result.get("pending_confirmation", False),
        "confirmation_type": result.get("confirmation_type"),
        "confirmation_prompt": result.get("confirmation_prompt"),
        "artifacts": result.get("artifacts", []),
        "tool_transparency": result.get("tool_transparency", []),
        "thread_id": result.get("thread_id"),
    }
