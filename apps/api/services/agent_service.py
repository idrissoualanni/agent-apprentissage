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
    "needs_diagnostic": False,
    "diagnostic_just_completed": False,
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
    session_id=None,
) -> dict:
    """Construit l'etat d'entree sans ecraser l'etat persistant du thread.

    - Premier tour d'un nouveau thread : STATE_DEFAULTS complet.
    - Tours suivants : uniquement les champs du tour courant ; l'etat
      persistant (diagnostic en cours, memoire de session, ...) est
      restaure par le checkpointer.

    NB : session_id est (re)injecté à chaque tour APRÈS _PER_TURN_RESETS afin
    que la boucle mémoire fonctionne : session_memory_node persiste le résumé
    compacté en DB et context_builder_node recharge le contexte de session.
    """
    initial_state = {
        "question": question,
        "user_id": user_id,
        "thread_id": thread_id,
        "model_override": model_override,
        "force_web_search": force_web_search,
        "streaming": streaming,
        **_PER_TURN_RESETS,
        "session_id": session_id,
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


def _get_pending_interrupt(graph, config_dict: dict):
    """Retourne le payload de l'interrupt en attente sur ce thread, sinon None."""
    try:
        snapshot = graph.get_state(config_dict)
        if snapshot is None or not snapshot.next:
            return None
        for task in getattr(snapshot, "tasks", None) or []:
            interrupts = getattr(task, "interrupts", None)
            if interrupts:
                return interrupts[0].value
        return None
    except Exception:
        return None


def _extract_interrupt(final_state) -> Optional[dict]:
    """Extrait le payload d'un interrupt de l'etat retourne par invoke()."""
    if not isinstance(final_state, dict):
        return None
    interrupts = final_state.get("__interrupt__")
    if not interrupts:
        return None
    try:
        value = interrupts[0].value
        if isinstance(value, dict):
            return value
        return {"question": str(value), "type": None}
    except Exception:
        return None


def run_agent(
    question: str,
    thread_id: Optional[str] = None,
    user_id: str = "default_user",
    user_confirmed: Optional[bool] = None,
    model_override: Optional[str] = None,
    force_web_search: bool = False,
    session_id: Optional[int] = None,
) -> dict:
    """Exécute l'agent sur une question et retourne la réponse.

    Args:
        question: Question utilisateur
        thread_id: ID de thread LangGraph (pour continuité conversationnelle)
        user_id: ID utilisateur V3
        user_confirmed: Confirmation HITL (True/False/None)
        model_override: Forcer un modèle spécifique
        force_web_search: Si True, force la méthode web_search
        session_id: ID de session DB (boucle mémoire court/long terme)

    Returns:
        dict avec answer, method, artifacts, tool_transparency, etc.
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    graph = get_graph()
    mm = _get_model_manager()

    config_dict = {"configurable": {"thread_id": thread_id}}

    # HITL : le thread a-t-il un interrupt en attente (confirmation demandee
    # au tour precedent) ?
    pending_interrupt = _get_pending_interrupt(graph, config_dict)

    if pending_interrupt is not None and user_confirmed is not None:
        # Reprise apres confirmation : Command(resume=...) realimente
        # l'appel interrupt() du noeud en pause.
        from langgraph.types import Command
        invoke_input = Command(resume=user_confirmed)
        logger.info(f"Reprise HITL: thread={thread_id[:8]}, confirmed={user_confirmed}")
    else:
        invoke_input = _build_initial_state(
            graph,
            config_dict,
            question=question,
            user_id=user_id,
            thread_id=thread_id,
            model_override=model_override,
            force_web_search=force_web_search,
            streaming=False,
            user_confirmed=user_confirmed,
            session_id=session_id,
        )

    logger.info(f"Exécution agent: question='{question[:50]}...', thread={thread_id[:8]}")

    try:
        final_state = graph.invoke(invoke_input, config=config_dict)
    except Exception as e:
        logger.error(f"Erreur agent: {e}", exc_info=True)
        return {
            "answer": f"Une erreur est survenue : {str(e)}",
            "method": "error",
            "thread_id": thread_id,
            "error": str(e),
        }

    # HITL : l'execution s'est-elle arretee sur un nouvel interrupt ?
    interrupt_payload = _extract_interrupt(final_state)
    if interrupt_payload is not None:
        return {
            "answer": interrupt_payload.get("question", ""),
            "method": final_state.get("method", "unknown") if isinstance(final_state, dict) else "unknown",
            "thread_id": thread_id,
            "artifacts": [],
            "tool_transparency": [],
            "pending_confirmation": True,
            "confirmation_type": interrupt_payload.get("type"),
            "confirmation_prompt": interrupt_payload.get("question"),
            "evaluation_score": None,
            "feynman_score": None,
            "leitner_action": None,
            "web_search_results": None,
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


def run_quiz_feedback(
    thread_id: str,
    user_id: str,
    competency_name: str,
    correct: int,
    total: int,
    answers: Optional[list] = None,
    session_id: Optional[int] = None,
) -> dict:
    """Réinjecte le résultat d'un quiz interactif DANS LangGraph.

    Le composant frontend a renvoyé le score (et éventuellement le détail des
    réponses) via FastAPI ; on relance le graphe avec une question synthétique
    décrivant le résultat, pour que l'agent produise un feedback adaptatif et
    propose la suite (révision, approfondissement, etc.). La continuité est
    assurée par le checkpointer (même thread_id).

    Args:
        thread_id: ID de thread LangGraph (continuité de la session)
        user_id: ID utilisateur
        competency_name: Nom de la compétence évaluée
        correct: Nombre de bonnes réponses
        total: Nombre total de questions
        answers: Détail optionnel [{question, selected, correct, is_correct}]

    Returns:
        dict run_agent (answer, method, artifacts, ...)
    """
    ratio = (correct / total) if total else 0.0
    detail = ""
    if answers:
        wrong = [a for a in answers if not a.get("is_correct", True)]
        if wrong:
            detail = " Questions ratées : " + " ; ".join(
                str(w.get("question", ""))[:80] for w in wrong[:3]
            )

    question = (
        f"[RÉSULTAT DE QUIZ] Je viens d'obtenir {correct}/{total} ({ratio:.0%}) "
        f"au quiz sur « {competency_name} ».{detail} "
        f"Fais-moi un retour adapté à ce score et propose-moi la suite."
    )
    return run_agent(question=question, thread_id=thread_id, user_id=user_id,
                     session_id=session_id)


def run_agent_streaming(
    question: str,
    thread_id: Optional[str] = None,
    user_id: str = "default_user",
    model_override: Optional[str] = None,
    force_web_search: bool = False,
    session_id: Optional[int] = None,
    resume_value=None,
):
    """Exécute l'agent en mode streaming (yield token par token).

    Yields des dict avec les champs:
    - token: texte incrémental
    - done: True à la fin
    - metadata: dict avec method, artifacts, tool_transparency
    - interrupt: payload HITL si le graphe s'est arrêté sur interrupt()

    Args:
        resume_value: si fourni (True/False), reprend un interrupt en
            attente via Command(resume=...) au lieu d'une nouvelle question.
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    graph = get_graph()

    config_dict = {"configurable": {"thread_id": thread_id}}

    if resume_value is not None:
        # Reprise HITL : Command(resume=...) realimente l'appel interrupt()
        from langgraph.types import Command
        invoke_input = Command(resume=resume_value)
    else:
        invoke_input = _build_initial_state(
            graph,
            config_dict,
            question=question,
            user_id=user_id,
            thread_id=thread_id,
            model_override=model_override,
            force_web_search=force_web_search,
            streaming=True,
            session_id=session_id,
        )

    logger.info(f"Exécution agent streaming: thread={thread_id[:8]}")

    full_answer = ""
    try:
        for event in graph.stream(invoke_input, config=config_dict):
            for node_name, node_output in event.items():
                if node_output and "answer" in node_output and node_output["answer"]:
                    answer = node_output["answer"]
                    if answer != full_answer:
                        new_text = answer[len(full_answer):]
                        full_answer = answer
                        yield {"token": new_text, "done": False}

        # Etat final : method, artifacts et interrupt eventuel (HITL)
        method, artifacts, transparency, interrupt_payload = None, [], [], None
        try:
            snapshot = graph.get_state(config_dict)
            if snapshot is not None:
                values = snapshot.values or {}
                method = values.get("method")
                artifacts = values.get("artifacts", [])
                transparency = values.get("tool_transparency", [])
                if snapshot.next:
                    for task in getattr(snapshot, "tasks", None) or []:
                        interrupts = getattr(task, "interrupts", None)
                        if interrupts:
                            interrupt_payload = interrupts[0].value
                            break
        except Exception:
            pass

        yield {
            "token": "",
            "done": True,
            "metadata": {
                "thread_id": thread_id,
                "method": method,
                "artifacts": artifacts,
                "tool_transparency": transparency,
            },
            "interrupt": interrupt_payload,
        }
    except Exception as e:
        logger.error(f"Erreur agent streaming: {e}", exc_info=True)
        yield {"token": "", "done": True, "error": str(e)}
