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

    def diagnostic_wrapper(state):
        return nodes.diagnostic_node(state, model_name, db_path)

    def retrieval_wrapper(state):
        return nodes.retrieval_node(state, retriever)

    def method_wrapper(state):
        return nodes.method_selection_node(state)

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
    workflow.add_node("diagnostic", diagnostic_wrapper)
    workflow.add_node("retrieve", retrieval_wrapper)
    workflow.add_node("method", method_wrapper)
    workflow.add_node("generate", generate_wrapper)
    workflow.add_node("tool", tool_wrapper)
    workflow.add_node("evaluate", eval_wrapper)

    # Arêtes
    workflow.add_edge(START, "router")

    # Router → diagnostic ou retrieve
    def route_after_router(state):
        if state.get("method") == "diagnostic":
            return "diagnostic"
        return "retrieve"

    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {"diagnostic": "diagnostic", "retrieve": "retrieve"},
    )

    # Diagnostic → generate
    workflow.add_edge("diagnostic", "generate")

    # Retrieve → method → generate
    workflow.add_edge("retrieve", "method")

    # Method → generate ou tool
    def route_after_method(state):
        if state.get("method") in ("quiz", "feynman"):
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
