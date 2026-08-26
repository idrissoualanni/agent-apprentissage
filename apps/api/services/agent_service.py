"""Service d'orchestration de l'agent — exécution du graphe LangGraph V3."""

import uuid
import logging
from typing import Optional
from pathlib import Path

from apps.api.agent.graph import build_agent_graph
from apps.api.agent.state import STATE_DEFAULTS
from apps.api.services.model_manager import ModelManager
from apps.api.rag import retriever as retriever_mod
from apps.api.db import crud
import apps.api.config as config

logger = logging.getLogger(__name__)

_graph_instance = None
_model_manager = None
_retriever = None


def _get_model_manager() -> ModelManager:
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


def _get_retriever():
    global _retriever
    if _retriever is None:
        try:
            _retriever = retriever_mod.get_or_create_retriever(
                model_name=config.OLLAMA_EMBEDDING_MODEL,
                top_k=config.TOP_K,
                persist_dir=str(config.CHROMA_DIR),
            )
        except Exception as e:
            # En production sans embeddings disponibles (Ollama local absent),
            # on degrade gracieusement : le RAG retourne un retriever vide.
            logger.warning(f"Retriever indisponible ({e}); RAG desactive.")
            _retriever = _EmptyRetriever()
    return _retriever


class _EmptyRetriever:
    """Retriever vide utilise quand les embeddings sont indisponibles."""

    def invoke(self, query, **kwargs):
        return []

    def get_relevant_documents(self, query, **kwargs):
        return []


def get_graph():
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_agent_graph(
            retriever=_get_retriever(),
            model_manager=_get_model_manager(),
            db_path=config.DB_PATH,
        )
    return _graph_instance


# Champs a reinitialiser A CHAQUE TOUR (resultats du tour courant).
# Les champs persistants (diagnostic, chat_history, turn_count,
# session_summary, learner_context, last_method_success, ...) ne doivent
# SURTOUT PAS etre reinjectues : ils sont conserves par le checkpointer
# LangGraph et les ecraser casserait la continuite multi-tours.
_PER_TURN_RESETS = {
    "rag_confidence": None,
    "rag_relevant": False,
    "rag_reason": "",
    "tool_transparency": [],
    "artifacts": [],
    "web_search_results": None,
    "session_id": None,
    "next_step": None,
}


def _build_initial_state(
    graph,
    config_dict: dict,
    question: str,
    user_id: str,
    thread_id: str,
    model_override=None,
    force_web_search: bool = False,
    streaming: bool = False,
    user_confirmed=None,
) -> dict:
    """Construit l'etat d'entree sans ecraser l'etat persistant du thread.

    - Premier tour d'un nouveau thread : STATE_DEFAULTS complet.
    - Tours suivants : uniquement les champs du tour courant ; l'etat
      persistant (diagnostic en cours, memoire de session, ...) est
      restaure par le checkpointer.
    """
    initial_state = {
        "question": question,
        "user_id": user_id,
        "thread_id": thread_id,
        "model_override": model_override,
        "force_web_search": force_web_search,
        "streaming": streaming,
        **_PER_TURN_RESETS,
    }
    if user_confirmed is not None:
        initial_state["user_confirmed"] = user_confirmed

    has_state = False
    try:
        snapshot = graph.get_state(config_dict)
        has_state = bool(snapshot is not None and snapshot.values)
    except Exception:
        has_state = False

    if not has_state:
        initial_state = {**STATE_DEFAULTS, **initial_state}
    return initial_state


def run_agent(
    question: str,
    thread_id: Optional[str] = None,
    user_id: str = "default_user",
    user_confirmed: Optional[bool] = None,
    model_override: Optional[str] = None,
    force_web_search: bool = False,
) -> dict:
    """Exécute l'agent sur une question et retourne la réponse.

    Args:
        question: Question utilisateur
        thread_id: ID de thread LangGraph (pour continuité conversationnelle)
        user_id: ID utilisateur V3
        user_confirmed: Confirmation HITL (True/False/None)
        model_override: Forcer un modèle spécifique
        force_web_search: Si True, force la méthode web_search

    Returns:
        dict avec answer, method, artifacts, tool_transparency, etc.
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    graph = get_graph()
    mm = _get_model_manager()

    config_dict = {"configurable": {"thread_id": thread_id}}

    initial_state = _build_initial_state(
        graph,
        config_dict,
        question=question,
        user_id=user_id,
        thread_id=thread_id,
        model_override=model_override,
        force_web_search=force_web_search,
        streaming=False,
        user_confirmed=user_confirmed,
    )

    logger.info(f"Exécution agent: question='{question[:50]}...', thread={thread_id[:8]}")

    try:
        final_state = graph.invoke(initial_state, config=config_dict)
    except Exception as e:
        logger.error(f"Erreur agent: {e}", exc_info=True)
        return {
            "answer": f"Une erreur est survenue : {str(e)}",
            "method": "error",
            "thread_id": thread_id,
            "error": str(e),
        }

    return {
        "answer": final_state.get("answer", ""),
        "method": final_state.get("method", "unknown"),
        "thread_id": thread_id,
        "artifacts": final_state.get("artifacts", []),
        "tool_transparency": final_state.get("tool_transparency", []),
        "pending_confirmation": final_state.get("pending_confirmation", False),
        "confirmation_type": final_state.get("confirmation_type"),
        "confirmation_prompt": final_state.get("confirmation_prompt"),
        "evaluation_score": final_state.get("evaluation_score"),
        "feynman_score": final_state.get("feynman_score"),
        "leitner_action": final_state.get("leitner_action"),
        "web_search_results": final_state.get("web_search_results"),
    }


def run_agent_streaming(
    question: str,
    thread_id: Optional[str] = None,
    user_id: str = "default_user",
    model_override: Optional[str] = None,
    force_web_search: bool = False,
):
    """Exécute l'agent en mode streaming (yield token par token).

    Yields des dict avec les champs:
    - token: texte incrémental
    - done: True à la fin
    - metadata: dict avec method, artifacts, etc.
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    graph = get_graph()

    config_dict = {"configurable": {"thread_id": thread_id}}

    initial_state = _build_initial_state(
        graph,
        config_dict,
        question=question,
        user_id=user_id,
        thread_id=thread_id,
        model_override=model_override,
        force_web_search=force_web_search,
        streaming=True,
    )

    logger.info(f"Exécution agent streaming: thread={thread_id[:8]}")

    full_answer = ""
    try:
        for event in graph.stream(initial_state, config=config_dict):
            for node_name, node_output in event.items():
                if "answer" in node_output and node_output["answer"]:
                    answer = node_output["answer"]
                    if answer != full_answer:
                        new_text = answer[len(full_answer):]
                        full_answer = answer
                        yield {"token": new_text, "done": False}

        # Correctif 2 : récupérer les artefacts de l'état final
        artifacts = []
        try:
            final_state = graph.get_state(config_dict)
            artifacts = final_state.values.get("artifacts", []) if final_state else []
        except Exception:
            pass

        yield {
            "token": "",
            "done": True,
            "metadata": {
                "thread_id": thread_id,
                "method": full_answer and "completed",
                "artifacts": artifacts,
            },
        }
    except Exception as e:
        logger.error(f"Erreur agent streaming: {e}", exc_info=True)
        yield {"token": "", "done": True, "error": str(e)}
