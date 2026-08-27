"""Construction du StateGraph LangGraph V3 — orchestration de l'agent."""

import sqlite3
import logging
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from apps.api.agent.state import AgentState

logger = logging.getLogger(__name__)

CHECKPOINT_DB = Path(__file__).resolve().parent.parent.parent.parent / "checkpoints.db"


def build_agent_graph(retriever, model_manager, db_path=None, with_checkpointer=True):
    """Construit et compile le graphe de l'agent d'apprentissage V3.

    Args:
        retriever: ChromaDB retriever
        model_manager: ModelManager instance (fournit les LLMs)
        db_path: chemin vers la base SQLite
        with_checkpointer: si False, compile sans checkpointer SQLite
                           (utile pour LangGraph Studio qui gère le sien)
    """
    from apps.api.agent.nodes import (
        router_profil_node,
        diagnostic_node,
        retrieval_node,
        method_selection_node,
        answer_processing_node,
        generate_node,
        tool_execution_node,
        evaluation_memory_node,
        confirmation_node,
    )
    from apps.api.agent.nodes_context import (
        competency_proposer_node,
        context_builder_node,
        method_evaluator_node,
    )
    from apps.api.agent.memory.session_memory import session_memory_node

    logger.info("Construction du StateGraph V3...")

    # Wrappers pour injecter les dépendances
    def router_wrapper(state):
        return router_profil_node(state, retriever, model_manager, db_path)

    def answer_processing_wrapper(state):
        return answer_processing_node(state, model_manager, db_path)

    def diagnostic_wrapper(state):
        return diagnostic_node(state, model_manager, db_path)

    def retrieval_wrapper(state):
        return retrieval_node(state, retriever, model_manager)

    def method_wrapper(state):
        return method_selection_node(state, model_manager, db_path)

    def generate_wrapper(state):
        return generate_node(state, model_manager)

    def tool_wrapper(state):
        return tool_execution_node(state, model_manager)

    def eval_wrapper(state):
        return evaluation_memory_node(state, db_path)

    def confirmation_wrapper(state):
        return confirmation_node(state)

    def competency_proposer_wrapper(state):
        return competency_proposer_node(state, model_manager, db_path)

    def context_builder_wrapper(state):
        return context_builder_node(state, db_path)

    def session_memory_wrapper(state):
        return session_memory_node(state, model_manager, db_path)

    def method_evaluator_wrapper(state):
        return method_evaluator_node(state, model_manager, db_path)

    # Construction du graphe
    workflow = StateGraph(AgentState)

    # Nœuds
    workflow.add_node("router", router_wrapper)
    workflow.add_node("answer_processing", answer_processing_wrapper)
    workflow.add_node("diagnostic", diagnostic_wrapper)
    workflow.add_node("retrieve", retrieval_wrapper)
    workflow.add_node("method", method_wrapper)
    workflow.add_node("confirmation", confirmation_wrapper)
    workflow.add_node("generate", generate_wrapper)
    workflow.add_node("tool", tool_wrapper)
    workflow.add_node("evaluate", eval_wrapper)
    workflow.add_node("competency_proposer", competency_proposer_wrapper)
    workflow.add_node("context_builder", context_builder_wrapper)
    workflow.add_node("session_memory", session_memory_wrapper)
    workflow.add_node("method_evaluator", method_evaluator_wrapper)

    # Arêtes
    # Phase 4 : context_builder charge le Learner Model avant toute décision.
    workflow.add_edge(START, "context_builder")
    workflow.add_edge("context_builder", "router")

    def route_after_router(state):
        # Correctif 1 : diagnostic déjà en cours → traiter la réponse courante
        if state.get("diagnostic_active"):
            return "answer_processing"
        # V3 : le router ne code plus la méthode en dur ; il pose le flag
        # needs_diagnostic (bootstrap : aucun domaine ni niveau connu).
        if state.get("needs_diagnostic"):
            return "diagnostic"
        # Phase 3 : passer par competency_proposer (propose une compétence si aucune
        # n'est détectée ; transparent sinon).
        return "competency_proposer"

    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {"diagnostic": "diagnostic", "answer_processing": "answer_processing", "competency_proposer": "competency_proposer"},
    )

    def route_after_competency_proposer(state):
        if state.get("rag_needed") is False:
            return "method"
        return "answer_processing"

    workflow.add_conditional_edges(
        "competency_proposer",
        route_after_competency_proposer,
        {"method": "method", "answer_processing": "answer_processing"},
    )

    def route_after_answer_processing(state):
        # Correctif 1 : diagnostic en cours → on a posé une question, on attend la réponse
        if state.get("diagnostic_active"):
            return "session_memory"
        # V3 : le diagnostic vient de se terminer CE tour-ci (flag par tour,
        # réinitialisé à chaque tour) → message de niveau déjà dans answer.
        # Remplace l'ancien test method=="diagnostic" qui fuyait en stale au tour suivant.
        if state.get("diagnostic_just_completed"):
            return "session_memory"
        if state.get("evaluation_score") is not None or state.get("feynman_score") is not None:
            return "evaluate"
        if state.get("quiz_active") and not state.get("evaluation_score"):
            return "method"
        if state.get("awaiting_feynman_explanation") and not state.get("feynman_explanation"):
            return "method"
        return "retrieve"

    workflow.add_conditional_edges(
        "answer_processing",
        route_after_answer_processing,
        {"evaluate": "evaluate", "retrieve": "retrieve", "method": "method", "session_memory": "session_memory"},
    )

    # Correctif : le diagnostic pose sa question puis passe par session_memory
    # (pas de passage par generate, qui écraserait la question posée)
    workflow.add_edge("diagnostic", "session_memory")
    workflow.add_edge("retrieve", "method")

    def route_after_method(state):
        if state.get("method") in ("quiz", "feynman", "artifact"):
            return "confirmation"
        if state.get("method") in ("web_search", "revision", "wikipedia"):
            return "tool"
        return "generate"

    workflow.add_conditional_edges(
        "method",
        route_after_method,
        {"confirmation": "confirmation", "tool": "tool", "generate": "generate"},
    )

    def route_after_confirmation(state):
        # Avec interrupt(), la confirmation est déjà résolue quand on arrive ici.
        # user_confirmed=True + méthode outil → on exécute le tool.
        if state.get("user_confirmed") is True and state.get("method") in ("quiz", "feynman", "artifact"):
            return "tool"
        # Refus (méthode repassée en scaffold) ou autre cas → génération directe.
        return "generate"

    workflow.add_conditional_edges(
        "confirmation",
        route_after_confirmation,
        {"tool": "tool", "generate": "generate"},
    )

    workflow.add_edge("tool", "evaluate")
    # Phase 5 : method_evaluator met a jour method_effectiveness + mastery blend.
    workflow.add_edge("evaluate", "method_evaluator")
    workflow.add_edge("method_evaluator", "generate")
    # Phase 4 : tous les chemins passent par session_memory avant la fin.
    workflow.add_edge("generate", "session_memory")
    workflow.add_edge("session_memory", END)

    # Checkpointer SQLite persistant (optionnel, pour LangGraph Studio)
    if with_checkpointer:
        CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        app = workflow.compile(checkpointer=checkpointer)
        logger.info(f"Graphe V3 compilé avec checkpointer SQLite : {CHECKPOINT_DB}")
    else:
        app = workflow.compile()
        logger.info("Graphe V3 compilé SANS checkpointer (mode Studio)")

    return app
