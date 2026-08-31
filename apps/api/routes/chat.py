"""Routes chat — SSE streaming + HITL confirmation."""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from apps.api.services import agent_service
from apps.api.services.streaming import stream_tokens, stream_json_response
from apps.api.services.checkpoint import get_thread_id_from_session
from apps.api.db import crud
import apps.api.config as config

router = APIRouter(tags=["chat"])

# Longueur max d'une question : ~4 pages. Au-delà, le prompt moteur deviendrait
# démesuré ; l'utilisateur doit découper sa demande.
MAX_QUESTION_LENGTH = 4000


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_LENGTH)
    session_id: Optional[int] = Field(None, ge=1)
    thread_id: Optional[str] = Field(None, min_length=1, max_length=128)
    user_id: str = Field("default_user", min_length=1, max_length=64)
    streaming: bool = False
    model_override: Optional[str] = Field(None, min_length=1, max_length=128)
    force_web_search: bool = False

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        """Refuse une question composée uniquement d'espaces."""
        if not v.strip():
            raise ValueError("La question ne peut pas être vide")
        return v


class ConfirmationRequest(BaseModel):
    session_id: Optional[int] = Field(None, ge=1)
    thread_id: Optional[str] = Field(None, min_length=1, max_length=128)
    user_id: str = Field("default_user", min_length=1, max_length=64)
    accepted: bool


class QuizAnswer(BaseModel):
    """Une réponse d'une question du quiz interactif.

    En miroir du frontend (QuizAnswerDetail, lib/types.ts) : les données du
    quiz sont contrôlées à l'entrée, elles ne transitent plus en `list` brute.
    """
    question: str = Field(..., min_length=1, max_length=2000)
    selected: Optional[int] = Field(None, ge=0, le=20)
    correct: Optional[int] = Field(None, ge=0, le=20)
    is_correct: bool = True


class QuizSubmitRequest(BaseModel):
    """Soumission du résultat d'un quiz interactif (artefact <learning_artefact>).

    Le format de sortie du quiz porte assez de métadonnées (competency_id,
    identifier, niveau) pour que FastAPI puisse renvoyer le résultat DANS
    LangGraph et obtenir un feedback adaptatif de l'agent.
    """
    session_id: Optional[int] = Field(None, ge=1)
    thread_id: Optional[str] = Field(None, min_length=1, max_length=128)
    competency_id: Optional[int] = Field(None, ge=1)
    competency_name: Optional[str] = Field(None, min_length=1, max_length=200)
    artifact_id: Optional[str] = Field(None, min_length=1, max_length=128)
    correct: int = Field(..., ge=0, le=100)
    total: int = Field(..., ge=1, le=100)
    answers: Optional[list[QuizAnswer]] = None
    user_id: str = Field("default_user", min_length=1, max_length=64)
    trigger_agent: bool = True                 # relancer LangGraph pour le feedback

    @field_validator("answers")
    @classmethod
    def answers_count_matches(cls, v, info):
        """Le nombre de réponses doit correspondre au total déclaré."""
        total = info.data.get("total")
        if v is not None and total is not None and len(v) != total:
            raise ValueError(f"answers contient {len(v)} éléments, mais total = {total}")
        return v


@router.post("")
def chat(req: ChatRequest):
    """Point d'entrée principal — envoie une question à l'agent.

    Accepte session_id (frontend) OU thread_id (direct).
    Retourne SSE si streaming=True, JSON sinon.

    NB : `def` (et non `async def`) pour que l'appel bloquant run_agent
    s'execute dans le pool de threads sans bloquer l'event loop.
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
            session_id=req.session_id,
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
            session_id=req.session_id,
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
def confirm_action(req: ConfirmationRequest):
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
        session_id=req.session_id,
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
def quiz_submit(req: QuizSubmitRequest):
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

    # Feedback adaptatif "statique" selon le ratio (utilisé si l'agent n'est pas relancé)
    if ratio >= 0.7:
        feedback = f"Excellent ! {req.correct}/{req.total}. Tu maîtrises bien ce sujet."
        suggestion = "approfondir"
    elif ratio >= 0.4:
        feedback = f"Bien joué ! {req.correct}/{req.total}. Encore un petit effort."
        suggestion = "continuer"
    else:
        feedback = f"{req.correct}/{req.total}. Pas de souci, on va reprendre les bases."
        suggestion = "expliquer"

    # BOUCLE INTERACTIVE : réinjecter le résultat DANS LangGraph pour que
    # l'agent produise un feedback adaptatif et propose la suite.
    agent_feedback = None
    agent_answer = None
    if req.trigger_agent:
        thread_id = req.thread_id
        if not thread_id and req.session_id:
            thread_id = get_thread_id_from_session(req.session_id)
        if thread_id:
            try:
                result = agent_service.run_quiz_feedback(
                    thread_id=thread_id,
                    user_id=req.user_id,
                    competency_name=req.competency_name or "ce sujet",
                    correct=req.correct,
                    total=req.total,
                    # run_quiz_feedback attend des dicts {is_correct, ...},
                    # pas des objets QuizAnswer.
                    answers=[a.model_dump() for a in req.answers] if req.answers else None,
                    session_id=req.session_id,
                )
                agent_answer = result.get("answer", "")
                agent_feedback = {
                    "answer": agent_answer,
                    "method": result.get("method"),
                    "artifacts": result.get("artifacts", []),
                    "thread_id": result.get("thread_id"),
                }
                # Sauvegarder le feedback de l'agent dans la session.
                if req.session_id and agent_answer:
                    try:
                        crud.add_message(
                            session_id=req.session_id,
                            role="assistant",
                            content=agent_answer,
                            method_used=result.get("method"),
                            user_id=req.user_id,
                            db_path=config.DB_PATH,
                        )
                    except Exception:
                        pass
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Échec feedback agent: {e}")

    return {
        "correct": req.correct,
        "total": req.total,
        "ratio": round(ratio, 2),
        "mastery": mastery,
        "feedback": feedback,
        "suggestion": suggestion,
        "agent_feedback": agent_feedback,
    }
