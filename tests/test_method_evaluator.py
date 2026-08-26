"""Tests Phase 5 — method evaluator + hook epsilon-greedy."""

import sqlite3


def _seed(db_path, competency_id=1, mastery_score=0.5):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO competency (id, domain, nom) VALUES (?, 'Python', 'variables')",
        (competency_id,),
    )
    conn.execute(
        "INSERT INTO mastery (competency_id, score, leitner_box, status) VALUES (?, ?, 1, 'learning')",
        (competency_id, mastery_score),
    )
    conn.commit()
    conn.close()


def test_method_evaluator_updates_effectiveness(tmp_db):
    from apps.api.agent.nodes_context import method_evaluator_node
    from apps.api.agent.memory import learner_model as lm

    _seed(tmp_db)
    state = {
        "method": "quiz",
        "active_competency": "variables",
        "evaluation_score": 0.8,  # succes
        "learner_profile": {"domain": "Python"},
    }
    result = method_evaluator_node(state, model_manager=None, db_path=tmp_db)
    assert result["last_method_success"] is True
    eff = lm.get_method_effectiveness(1, db_path=tmp_db)
    assert eff["quiz"]["uses"] == 1
    assert eff["quiz"]["successes"] == 1


def test_method_evaluator_blends_mastery_quiz(tmp_db):
    from apps.api.agent.nodes_context import method_evaluator_node
    from apps.api.db import crud

    _seed(tmp_db, mastery_score=0.5)
    state = {
        "method": "quiz",
        "active_competency": "variables",
        "evaluation_score": 1.0,
        "learner_profile": {"domain": "Python"},
    }
    method_evaluator_node(state, model_manager=None, db_path=tmp_db)
    m = crud.get_mastery(1, db_path=tmp_db)
    # Blend quiz : old*0.6 + new*0.4 = 0.5*0.6 + 1.0*0.4 = 0.7
    assert abs(m["score"] - 0.7) < 1e-3


def test_method_evaluator_blends_mastery_feynman(tmp_db):
    from apps.api.agent.nodes_context import method_evaluator_node
    from apps.api.db import crud

    _seed(tmp_db, mastery_score=0.5)
    state = {
        "method": "feynman",
        "active_competency": "variables",
        "feynman_score": 1.0,
        "learner_profile": {"domain": "Python"},
    }
    method_evaluator_node(state, model_manager=None, db_path=tmp_db)
    m = crud.get_mastery(1, db_path=tmp_db)
    # Blend feynman : old*0.3 + new*0.7 = 0.5*0.3 + 1.0*0.7 = 0.85
    assert abs(m["score"] - 0.85) < 1e-3


def test_method_evaluator_skips_without_competency(tmp_db):
    from apps.api.agent.nodes_context import method_evaluator_node

    state = {
        "method": "quiz",
        "active_competency": None,
        "evaluation_score": 0.8,
    }
    result = method_evaluator_node(state, model_manager=None, db_path=tmp_db)
    assert result == {}


def test_epsilon_greedy_exploits_with_zero_epsilon(tmp_db):
    from apps.api.agent.nodes_context import _epsilon_greedy_method
    from apps.api.agent.memory import learner_model as lm

    _seed(tmp_db)
    # Enregistrer une methode efficace
    lm.record_method_outcome(1, "scaffold", success=True, db_path=tmp_db)
    # epsilon=0 → toujours la methode par defaut (pas d'exploration)
    result = _epsilon_greedy_method(1, "socratic", db_path=tmp_db, epsilon=0.0)
    assert result == "socratic"


def test_epsilon_greedy_returns_known_method(tmp_db):
    from apps.api.agent.nodes_context import _epsilon_greedy_method
    from apps.api.agent.memory import learner_model as lm

    _seed(tmp_db)
    lm.record_method_outcome(1, "scaffold", success=True, db_path=tmp_db)
    # epsilon=1 → toujours exploration, mais doit retourner une methode connue
    result = _epsilon_greedy_method(1, "socratic", db_path=tmp_db, epsilon=1.0)
    assert result in ("scaffold",)
