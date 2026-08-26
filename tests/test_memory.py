"""Tests Phase 1 — memoire de session : chat_history rempli + checkpointer."""

from langchain_core.messages import HumanMessage, AIMessage


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    """LLM factice : repond sans appel reseau."""

    def invoke(self, messages, **kwargs):
        return _FakeResponse("Ceci est une reponse factice pour les tests.")


class _FakeModelManager:
    """ModelManager factice : retourne un FakeLLM pour toute operation."""

    def get_llm(self, operation):
        return _FakeLLM()


def _seed_profile_with_domain(db_path):
    """Definit un domaine dans le profil pour eviter la branche diagnostic."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    # S'assure qu'un profil existe puis lui donne un domaine.
    conn.execute(
        "INSERT OR IGNORE INTO learner_profile (user_id, domain) VALUES ('default_user', '')"
    )
    conn.execute(
        "UPDATE learner_profile SET domain = 'Python' WHERE user_id = 'default_user'"
    )
    conn.commit()
    conn.close()


def test_chat_history_filled_after_one_turn(tmp_db, mock_retriever):
    from apps.api.agent.graph import build_agent_graph

    _seed_profile_with_domain(tmp_db)
    g = build_agent_graph(
        mock_retriever, _FakeModelManager(), db_path=str(tmp_db), with_checkpointer=True
    )
    cfg = {"configurable": {"thread_id": "t-mem-1"}}
    g.invoke({"question": "Bonjour", "chat_history": []}, config=cfg)
    state = g.get_state(cfg).values
    history = state.get("chat_history", [])
    assert len(history) >= 1, "chat_history doit contenir au moins la question"
    assert any(isinstance(m, HumanMessage) for m in history), "la question doit etre un HumanMessage"


def test_chat_history_persists_across_turns(tmp_db, mock_retriever):
    from apps.api.agent.graph import build_agent_graph

    _seed_profile_with_domain(tmp_db)
    g = build_agent_graph(
        mock_retriever, _FakeModelManager(), db_path=str(tmp_db), with_checkpointer=True
    )
    cfg = {"configurable": {"thread_id": "t-mem-2"}}
    g.invoke({"question": "Premiere question"}, config=cfg)
    g.invoke({"question": "Deuxieme question"}, config=cfg)
    state = g.get_state(cfg).values
    history = state.get("chat_history", [])
    humans = [m for m in history if isinstance(m, HumanMessage)]
    assert len(humans) >= 2, f"les 2 questions doivent etre dans l'historique, got {len(humans)}"


def test_chat_history_isolated_per_thread(tmp_db, mock_retriever):
    from apps.api.agent.graph import build_agent_graph

    _seed_profile_with_domain(tmp_db)
    g = build_agent_graph(
        mock_retriever, _FakeModelManager(), db_path=str(tmp_db), with_checkpointer=True
    )
    cfg_a = {"configurable": {"thread_id": "t-mem-A"}}
    cfg_b = {"configurable": {"thread_id": "t-mem-B"}}
    g.invoke({"question": "Question A"}, config=cfg_a)
    g.invoke({"question": "Question B"}, config=cfg_b)
    hist_a = g.get_state(cfg_a).values.get("chat_history", [])
    hist_b = g.get_state(cfg_b).values.get("chat_history", [])
    humans_a = [m.content for m in hist_a if isinstance(m, HumanMessage)]
    humans_b = [m.content for m in hist_b if isinstance(m, HumanMessage)]
    assert "Question A" in humans_a and "Question B" not in humans_a
    assert "Question B" in humans_b and "Question A" not in humans_b
