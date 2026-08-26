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
    force_web_search: bool = False


class ConfirmationRequest(BaseModel):
    session_id: Optional[int] = None
    thread_id: Optional[str] = None
    user_id: str = "default_user"
    accepted: bool


class QuizSubmitRequest(BaseModel):
    """Correctif 2 : soumission du score d'un quiz interactif (artefact)."""
    session_id: Optional[int] = None
    competency_id: Optional[int] = None
    competency_name: Optional[str] = None
    correct: int
    total: int
    user_id: str = "default_user"


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
            force_web_search=req.force_web_search,
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
            force_web_search=req.force_web_search,
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
        # (retourner le dict directement : FastAPI le serialise en JSON)
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


@router.post("/quiz-submit")
async def quiz_submit(req: QuizSubmitRequest):
    """Correctif 2 : reçoit le score d'un quiz interactif et met à jour la maîtrise Leitner.

    Correctif 4 : retourne aussi un feedback adaptatif selon le ratio de réussite.
    """
    from apps.api.agent.tools.progress import update_mastery_from_score

    if req.total <= 0:
        raise HTTPException(400, "Le nombre total de questions doit être > 0")

    ratio = req.correct / req.total if req.total else 0.0

    # Mettre à jour la maîtrise si la compétence est connue
    mastery = None
    if req.competency_id is not None:
        try:
            result_str = update_mastery_from_score.invoke({
                "competency_id": req.competency_id,
                "correct": req.correct,
                "total": req.total,
            })
            mastery = json.loads(result_str)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Échec mise à jour maîtrise: {e}")

    # Enregistrer la tentative de quiz en DB
    if req.session_id and req.competency_id is not None:
        try:
            crud.record_quiz_attempt(
                competency_id=req.competency_id,
                question=f"Quiz {req.correct}/{req.total}",
                options="",
                user_answer=f"{req.correct}/{req.total}",
                is_correct=ratio >= 0.6,
                session_id=req.session_id,
                db_path=config.DB_PATH,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Échec enregistrement quiz: {e}")

    # Correctif 4 : feedback adaptatif selon le ratio
    if ratio >= 0.7:
        feedback = f"Excellent ! {req.correct}/{req.total}. Tu maîtrises bien ce sujet."
        suggestion = "approfondir"
    elif ratio >= 0.4:
        feedback = f"Bien joué ! {req.correct}/{req.total}. Encore un petit effort."
        suggestion = "continuer"
    else:
        feedback = f"{req.correct}/{req.total}. Pas de souci, on va reprendre les bases."
        suggestion = "expliquer"

    return {
        "correct": req.correct,
        "total": req.total,
        "ratio": round(ratio, 2),
        "mastery": mastery,
        "feedback": feedback,
        "suggestion": suggestion,
    }
