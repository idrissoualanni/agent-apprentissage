"""Endpoint WebSocket /ws/{session_id} — relie session DB ↔ thread LangGraph.

Spec : docs/superpowers/specs/2026-08-27-websocket-cache-design.md
- La connexion est validee contre la session DB (close 4404 si inconnue)
- Le thread LangGraph est resolu depuis la session (continuite checkpointer)
- Les messages sont sauvegardes dans la session (crud.add_message)
- L'agent tourne dans un thread ; tokens pousses via file asyncio
  (pont loop.call_soon_threadsafe — Queue.put direct depuis un thread
  n'est pas sur)
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.api.db import crud
from apps.api.services import agent_service
from apps.api.services.checkpoint import get_thread_id_from_session
from apps.api.ws.manager import manager
from apps.api.ws import protocol as p
import apps.api.config as config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


def _notify_due_reviews(session_id: int) -> None:
    """Pousse une notification si des revisions sont dues (fire-and-forget)."""
    try:
        from apps.api.agent.memory import revision_planner
        due = revision_planner.get_due_reviews(db_path=config.DB_PATH, limit=5)
        if due:
            asyncio.get_running_loop().create_task(manager.send(
                session_id,
                p.notification_msg("revision_due", {
                    "count": len(due),
                    "items": [d.get("competency_name", d.get("nom", "")) for d in due],
                }),
            ))
    except Exception:
        pass


async def _run_stream_to_socket(session_id: int, thread_id, user_id: str,
                                question: str, force_web_search: bool,
                                resume_value=None) -> None:
    """Execute l'agent (streaming) dans un thread et pousse les tokens."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def worker():
        try:
            for event in agent_service.run_agent_streaming(
                question=question,
                thread_id=thread_id,
                user_id=user_id,
                force_web_search=force_web_search,
                session_id=session_id,
                resume_value=resume_value,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as e:
            logger.error(f"WS agent error: {e}", exc_info=True)
            loop.call_soon_threadsafe(
                queue.put_nowait, {"token": "", "done": True, "error": str(e)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, worker)

    full_answer = ""
    final_meta = {}
    interrupt_payload = None
    error = None
    while True:
        event = await queue.get()
        if event is None:
            break
        if event.get("error"):
            error = event["error"]
        token = event.get("token")
        if token:
            full_answer += token
            await manager.send(session_id, p.token_msg(token))
        if event.get("interrupt"):
            interrupt_payload = event["interrupt"]
        if event.get("done"):
            final_meta = event.get("metadata", {}) or {}

    if error:
        await manager.send(session_id, p.error_msg(error))
        manager.set_busy(session_id, False)
        return

    # Interrupt (HITL) : demander confirmation, pas de message final complet
    if interrupt_payload is not None:
        payload = (interrupt_payload if isinstance(interrupt_payload, dict)
                   else {"question": str(interrupt_payload)})
        await manager.send(session_id, p.confirmation_request_msg(
            payload.get("type"), payload.get("question", "")))
        try:
            if question:
                crud.add_message(session_id=session_id, role="user",
                                 content=question, user_id=user_id,
                                 db_path=config.DB_PATH)
        except Exception:
            pass
        manager.set_busy(session_id, False)
        return

    # Message final + sauvegarde dans la session
    result = {
        "answer": full_answer,
        "method": final_meta.get("method"),
        "thread_id": thread_id,
        "artifacts": final_meta.get("artifacts", []),
        "tool_transparency": final_meta.get("tool_transparency", []),
    }
    try:
        if question:
            crud.add_message(session_id=session_id, role="user",
                             content=question, user_id=user_id,
                             db_path=config.DB_PATH)
        crud.add_message(session_id=session_id, role="assistant",
                         content=full_answer,
                         method_used=result["method"],
                         user_id=user_id, db_path=config.DB_PATH)
    except Exception as e:
        logger.warning(f"WS save message failed: {e}")

    await manager.send(session_id, p.final_message_msg(result))
    _notify_due_reviews(session_id)
    manager.set_busy(session_id, False)


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: int,
                             user_id: str = "default_user"):
    await websocket.accept()

    # Liaison session DB ↔ WebSocket
    session = crud.get_session(session_id, db_path=config.DB_PATH)
    if not session:
        await websocket.close(code=4404, reason="session_not_found")
        return

    # Liaison session ↔ thread LangGraph
    thread_id = get_thread_id_from_session(session_id)
    if not thread_id:
        thread_id = str(uuid.uuid4())
        try:
            with crud.get_connection(config.DB_PATH) as conn:
                conn.execute(
                    "UPDATE session SET langgraph_thread_id = ? WHERE id = ?",
                    (thread_id, session_id),
                )
        except Exception:
            pass

    await manager.connect(session_id, websocket)
    try:
        # Resync HITL : interrupt en attente dans le checkpoint → re-emission
        pending = agent_service._get_pending_interrupt(
            agent_service.get_graph(),
            {"configurable": {"thread_id": thread_id}},
        )
        if pending is not None:
            payload = (pending if isinstance(pending, dict)
                       else {"question": str(pending)})
            await manager.send(session_id, p.confirmation_request_msg(
                payload.get("type"), payload.get("question", "")))

        while True:
            data = await websocket.receive_json()
            mtype = data.get("type")

            if mtype == "ping":
                await manager.send(session_id, p.pong_msg())

            elif mtype == "chat":
                if manager.is_busy(session_id):
                    await manager.send(session_id, p.error_msg("agent_busy"))
                    continue
                question = (data.get("question") or "").strip()
                if not question:
                    await manager.send(session_id, p.error_msg("empty_question"))
                    continue
                manager.set_busy(session_id, True)
                asyncio.create_task(_run_stream_to_socket(
                    session_id, thread_id, user_id, question,
                    bool(data.get("force_web_search", False)),
                ))

            elif mtype == "confirm":
                if manager.is_busy(session_id):
                    await manager.send(session_id, p.error_msg("agent_busy"))
                    continue
                manager.set_busy(session_id, True)
                asyncio.create_task(_run_stream_to_socket(
                    session_id, thread_id, user_id, "",
                    False, resume_value=bool(data.get("accepted")),
                ))

            elif mtype == "quiz_submit":
                try:
                    from apps.api.agent.tools.progress import update_mastery_from_score
                    import json as _json
                    res = update_mastery_from_score.invoke({
                        "competency_id": data.get("competency_id"),
                        "correct": int(data.get("correct", 0)),
                        "total": int(data.get("total", 1)),
                    })
                    await manager.send(session_id, {
                        "type": "quiz_result",
                        "mastery": _json.loads(res),
                    })
                except Exception as e:
                    await manager.send(
                        session_id, p.error_msg(f"quiz_submit_failed: {e}"))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS error session={session_id}: {e}", exc_info=True)
    finally:
        manager.disconnect(session_id, websocket)
