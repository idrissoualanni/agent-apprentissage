"""Construction du StateGraph LangGraph V3 — orchestration de l'agent."""

import sqlite3
import logging
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from apps.api.agent.state import AgentState

logger = logging.getLogger(__name__)

CHECKPOINT_DB = Path(__file__).resolve().parent.parent.parent.parent / "checkpoints.db"


def build_agent_graph(retriever, model_manager, db_path=None):
    """Construit et compile le graphe de l'agent d'apprentissage V3.

    Args:
        retriever: ChromaDB retriever
        model_manager: ModelManager instance (fournit les LLMs)
        db_path: chemin vers la base SQLite
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

    logger.info("Construction du StateGraph V3...")

    # Wrappers pour injecter les dépendances
    def router_wrapper(state):
        return router_profil_node(state, retriever, model_manager, db_path)

    def answer_processing_wrapper(state):
        return answer_processing_node(state, db_path)

    def diagnostic_wrapper(state):
        return diagnostic_node(state, model_manager, db_path)

    def retrieval_wrapper(state):
        return retrieval_node(state, retriever)

    def method_wrapper(state):
        return method_selection_node(state, db_path)

    def generate_wrapper(state):
        return generate_node(state, model_manager)

    def tool_wrapper(state):
        return tool_execution_node(state, model_manager)

    def eval_wrapper(state):
        return evaluation_memory_node(state, db_path)

    def confirmation_wrapper(state):
        return confirmation_node(state)

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

    # Arêtes
    workflow.add_edge(START, "router")

    def route_after_router(state):
        if state.get("method") == "diagnostic":
            return "diagnostic"
        if state.get("rag_needed") is False:
            return "method"
        return "answer_processing"

    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {"diagnostic": "diagnostic", "answer_processing": "answer_processing", "method": "method"},
    )

    def route_after_answer_processing(state):
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
        {"evaluate": "evaluate", "retrieve": "retrieve", "method": "method"},
    )

    workflow.add_edge("diagnostic", "generate")
    workflow.add_edge("retrieve", "method")

    def route_after_method(state):
        if state.get("method") in ("quiz", "feynman", "artifact"):
            return "confirmation"
        if state.get("method") in ("web_search", "revision"):
            return "tool"
        return "generate"

    workflow.add_conditional_edges(
        "method",
        route_after_method,
        {"confirmation": "confirmation", "tool": "tool", "generate": "generate"},
    )

    def route_after_confirmation(state):
        if state.get("pending_confirmation"):
            return "__end__"
        if state.get("method") in ("quiz", "feynman", "artifact") and not state.get("answer"):
            return "tool"
        return "generate"

    workflow.add_conditional_edges(
        "confirmation",
        route_after_confirmation,
        {"tool": "tool", "generate": "generate", "__end__": END},
    )

    workflow.add_edge("tool", "evaluate")
    workflow.add_edge("evaluate", "generate")
    workflow.add_edge("generate", END)

    # Checkpointer SQLite persistant
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    app = workflow.compile(checkpointer=checkpointer)

    logger.info(f"Graphe V3 compilé avec checkpointer SQLite : {CHECKPOINT_DB}")
    return app
