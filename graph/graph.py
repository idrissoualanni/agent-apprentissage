"""Construction du StateGraph LangGraph — orchestration de l'agent."""

import sqlite3
from pathlib import Path
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from graph.state import AgentState
from graph import nodes

CHECKPOINT_DB = Path(__file__).resolve().parent.parent / "checkpoints.db"


def build_agent_graph(retriever, model_name: str, db_path=None):
    """Construit et compile le graphe de l'agent d'apprentissage."""
    print(f"[graph] Construction du StateGraph avec Ollama ({model_name})...")

    # Wrappers pour injecter les dépendances
    def router_wrapper(state):
        return nodes.router_profil_node(state, retriever, model_name, db_path)

    def answer_processing_wrapper(state):
        return nodes.answer_processing_node(state, db_path)

    def diagnostic_wrapper(state):
        return nodes.diagnostic_node(state, model_name, db_path)

    def retrieval_wrapper(state):
        return nodes.retrieval_node(state, retriever)

    def method_wrapper(state):
        return nodes.method_selection_node(state, db_path)

    def generate_wrapper(state):
        return nodes.generate_node(state, model_name)

    def tool_wrapper(state):
        return nodes.tool_execution_node(state, model_name)

    def eval_wrapper(state):
        return nodes.evaluation_memory_node(state, db_path)

    # Construction du graphe
    workflow = StateGraph(AgentState)

    # Nœuds
    workflow.add_node("router", router_wrapper)
    workflow.add_node("answer_processing", answer_processing_wrapper)
    workflow.add_node("diagnostic", diagnostic_wrapper)
    workflow.add_node("retrieve", retrieval_wrapper)
    workflow.add_node("method", method_wrapper)
    workflow.add_node("generate", generate_wrapper)
    workflow.add_node("tool", tool_wrapper)
    workflow.add_node("evaluate", eval_wrapper)

    # Arêtes
    workflow.add_edge(START, "router")

    # Router → diagnostic ou answer_processing
    def route_after_router(state):
        if state.get("method") == "diagnostic":
            return "diagnostic"
        return "answer_processing"

    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {"diagnostic": "diagnostic", "answer_processing": "answer_processing"},
    )

    # Answer_processing → evaluate (si quiz/feynman réponse) ou retrieve
    def route_after_answer_processing(state):
        # Si une évaluation a été déclenchée (quiz répondue ou Feynman évalué)
        if state.get("evaluation_score") is not None or state.get("feynman_score") is not None:
            return "evaluate"
        # Si on attend encore une réponse quiz/feynman, on génère direct
        if state.get("quiz_active") and not state.get("evaluation_score"):
            # Quiz actif mais pas encore évalué → on génère le prompt quiz
            return "method"
        if state.get("awaiting_feynman_explanation") and not state.get("feynman_explanation"):
            # Feynman en attente → on génère le prompt feynman
            return "method"
        # Sinon, on continue normalement
        return "retrieve"

    workflow.add_conditional_edges(
        "answer_processing",
        route_after_answer_processing,
        {
            "evaluate": "evaluate",
            "retrieve": "retrieve",
            "method": "method",
        },
    )

    # Diagnostic → generate
    workflow.add_edge("diagnostic", "generate")

    # Retrieve → method
    workflow.add_edge("retrieve", "method")

    # Method → generate ou tool
    def route_after_method(state):
        if state.get("method") in ("quiz", "feynman", "artifact"):
            return "tool"
        return "generate"

    workflow.add_conditional_edges(
        "method",
        route_after_method,
        {"tool": "tool", "generate": "generate"},
    )

    # Tool → evaluate → generate (pour formater la réponse)
    workflow.add_edge("tool", "evaluate")
    workflow.add_edge("evaluate", "generate")

    # Generate → END
    workflow.add_edge("generate", END)

    # Checkpointer SQLite persistant
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    app = workflow.compile(checkpointer=checkpointer)

    print(f"   -> Graphe compile avec checkpointer SQLite : {CHECKPOINT_DB}")
    return app
