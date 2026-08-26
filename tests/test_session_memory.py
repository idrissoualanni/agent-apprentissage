"""Tests Phase 4 — sous-agent memoire (session_memory) + context_builder."""

import sqlite3

from langchain_core.messages import HumanMessage, AIMessage


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeMemoryLLM:
    """Retourne un JSON de memoire valide."""

    def invoke(self, messages, **kwargs):
        return _FakeResponse(
            '{"competences_abordees": ["variables"], "niveau_estime": "debutant", '
            '"reussites": ["a compris les variables"], "erreurs_ou_lacunes": [], '
            '"resume_textuel": "Session sur les variables."}'
        )


class _FakeModelManager:
    def get_llm(self, operation):
        return _FakeMemoryLLM()


def _seed_session(db_path, session_id=1):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO session (id, user_id, langgraph_thread_id) VALUES (?, 'default_user', ?)",
        (session_id, f"thread-mem-{session_id}"),
    )
    conn.commit()
    conn.close()


def _history(n):
    """Construit un chat_history de n echanges."""
    h = []
    for i in range(n):
        h.append(HumanMessage(content=f"Question {i}"))
        h.append(AIMessage(content=f"Reponse {i}"))
    return h


def test_session_memory_compacts_at_interval(tmp_db):
    from apps.api.agent.memory.session_memory import session_memory_node, MEMORY_EVERY_N_TURNS

    _seed_session(tmp_db)
    state = {
        "chat_history": _history(3),
        "turn_count": MEMORY_EVERY_N_TURNS - 1,  # sera incremente a 3
        "session_id": 1,
        "user_id": "default_user",
    }
    result = session_memory_node(state, _FakeModelManager(), db_path=tmp_db)
    assert result["turn_count"] == MEMORY_EVERY_N_TURNS
    assert result.get("session_summary") is not None
    assert result["session_summary"]["pedagogical_facts"]["niveau_estime"] == "debutant"
    assert result["session_summary"]["text_summary"] == "Session sur les variables."


def test_session_memory_skips_off_interval(tmp_db):
    from apps.api.agent.memory.session_memory import session_memory_node

    _seed_session(tmp_db)
    state = {
        "chat_history": _history(2),
        "turn_count": 0,  # sera incremente a 1 (pas un multiple de 3)
        "session_id": 1,
        "user_id": "default_user",
    }
    result = session_memory_node(state, _FakeModelManager(), db_path=tmp_db)
    assert result["turn_count"] == 1
    assert "session_summary" not in result, "ne doit pas compacter hors intervalle"


def test_session_memory_persists_to_db(tmp_db):
    from apps.api.agent.memory.session_memory import session_memory_node, MEMORY_EVERY_N_TURNS
    from apps.api.agent.memory import learner_model as lm

    _seed_session(tmp_db)
    state = {
        "chat_history": _history(3),
        "turn_count": MEMORY_EVERY_N_TURNS - 1,
        "session_id": 1,
        "user_id": "default_user",
    }
    session_memory_node(state, _FakeModelManager(), db_path=tmp_db)
    stored = lm.get_session_summary(1, db_path=tmp_db)
    assert stored is not None
    assert stored["pedagogical_facts"]["niveau_estime"] == "debutant"


def test_context_builder_loads_learner_context(tmp_db):
    from apps.api.agent.nodes_context import context_builder_node
    from apps.api.agent.memory import learner_model as lm

    conn = sqlite3.connect(str(tmp_db))
    conn.execute("INSERT INTO competency (id, domain, nom) VALUES (1, 'Python', 'variables')")
    conn.execute(
        "INSERT INTO session (id, user_id, langgraph_thread_id) VALUES (1, 'default_user', 'thread-ctx')"
    )
    conn.commit()
    conn.close()
    lm.bump_topic("default_user", "variables", db_path=tmp_db)

    state = {"user_id": "default_user", "session_id": 1}
    result = context_builder_node(state, db_path=tmp_db)
    ctx = result["learner_context"]
    assert len(ctx["competencies"]) == 1
    assert ctx["competencies"][0]["nom"] == "variables"
    assert ctx["top_topics"][0]["topic"] == "variables"
