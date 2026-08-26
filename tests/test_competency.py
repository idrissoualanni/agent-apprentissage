"""Tests Phase 3 — competences dynamiques (pending_competency + proposer node)."""

import sqlite3


def _seed_domain(db_path, domain="Python"):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO learner_profile (user_id, domain) VALUES ('default_user', ?)",
        (domain,),
    )
    conn.execute("UPDATE learner_profile SET domain = ? WHERE user_id = 'default_user'", (domain,))
    conn.commit()
    conn.close()


def test_propose_and_get_pending_competency(tmp_db):
    from apps.api.agent.memory import learner_model as lm

    pid = lm.propose_competency("les decorators", "Python", db_path=tmp_db)
    assert pid is not None
    pending = lm.get_pending_competency("default_user", db_path=tmp_db)
    assert pending["proposed_name"] == "les decorators"
    assert pending["status"] == "pending"


def test_resolve_pending_competency(tmp_db):
    from apps.api.agent.memory import learner_model as lm

    pid = lm.propose_competency("les generators", "Python", db_path=tmp_db)
    lm.resolve_pending_competency(pid, "approved", db_path=tmp_db)
    # Une fois resolue, plus de pending
    assert lm.get_pending_competency("default_user", db_path=tmp_db) is None


def test_find_similar_competency(tmp_db):
    from apps.api.db import crud
    from apps.api.agent.memory import learner_model as lm

    crud.create_competency("Python", "variables", db_path=tmp_db)
    found = lm.find_similar_competency("Variables", "Python", db_path=tmp_db)
    assert found is not None and found["nom"] == "variables"
    not_found = lm.find_similar_competency("fonctions", "Python", db_path=tmp_db)
    assert not_found is None


def test_proposer_skips_when_competency_active(tmp_db):
    from apps.api.agent.nodes_context import competency_proposer_node

    _seed_domain(tmp_db)
    state = {
        "learner_profile": {"domain": "Python"},
        "question": "explique-moi les variables",
        "active_competency": "variables",
        "user_id": "default_user",
    }
    result = competency_proposer_node(state, model_manager=None, db_path=tmp_db)
    assert result == {}, "ne doit rien proposer si une competence est deja active"


def test_proposer_skips_when_no_domain(tmp_db):
    from apps.api.agent.nodes_context import competency_proposer_node

    state = {
        "learner_profile": {"domain": ""},
        "question": "bonjour",
        "active_competency": None,
        "user_id": "default_user",
    }
    result = competency_proposer_node(state, model_manager=None, db_path=tmp_db)
    assert result == {}, "ne doit rien proposer sans domaine"
