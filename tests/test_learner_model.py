"""Tests Phase 2 — Learner Model (base de connaissance utilisateur)."""

import sqlite3


def _seed(db_path, n_competencies=1, n_sessions=1):
    """Cree des competences et sessions de test."""
    conn = sqlite3.connect(str(db_path))
    for i in range(1, n_competencies + 1):
        conn.execute(
            "INSERT INTO competency (id, domain, nom) VALUES (?, 'Python', ?)",
            (i, f"competence_{i}"),
        )
    for i in range(1, n_sessions + 1):
        conn.execute(
            "INSERT INTO session (id, user_id, langgraph_thread_id) VALUES (?, 'default_user', ?)",
            (i, f"thread-test-{i}"),
        )
    conn.commit()
    conn.close()


def test_update_and_get_session_score(tmp_db):
    from apps.api.agent.memory import learner_model as lm

    _seed(tmp_db)
    lm.update_session_score(1, 1, 0.8, db_path=tmp_db)
    assert lm.get_session_score(1, 1, db_path=tmp_db) == 0.8
    # Upsert : mettre a jour le meme couple session/competence
    lm.update_session_score(1, 1, 0.95, db_path=tmp_db)
    assert lm.get_session_score(1, 1, db_path=tmp_db) == 0.95


def test_get_session_score_missing_returns_none(tmp_db):
    from apps.api.agent.memory import learner_model as lm

    _seed(tmp_db)
    assert lm.get_session_score(1, 1, db_path=tmp_db) is None


def test_record_method_outcome(tmp_db):
    from apps.api.agent.memory import learner_model as lm

    _seed(tmp_db)
    lm.record_method_outcome(1, "scaffold", success=True, db_path=tmp_db)
    lm.record_method_outcome(1, "scaffold", success=False, db_path=tmp_db)
    eff = lm.get_method_effectiveness(1, db_path=tmp_db)
    assert eff["scaffold"]["uses"] == 2
    assert eff["scaffold"]["successes"] == 1
    assert abs(eff["scaffold"]["effectiveness"] - 0.5) < 1e-6


def test_bump_and_get_topics(tmp_db):
    from apps.api.agent.memory import learner_model as lm

    lm.bump_topic("default_user", "variables", db_path=tmp_db)
    lm.bump_topic("default_user", "variables", db_path=tmp_db)
    lm.bump_topic("default_user", "boucles", db_path=tmp_db)
    topics = lm.get_top_topics("default_user", limit=5, db_path=tmp_db)
    assert topics[0]["topic"] == "variables"
    assert topics[0]["mentions"] == 2
    assert any(t["topic"] == "boucles" for t in topics)


def test_upsert_and_get_session_summary(tmp_db):
    from apps.api.agent.memory import learner_model as lm

    _seed(tmp_db)
    facts = {"niveau_estime": "intermediaire", "erreurs": ["confusion if/else"]}
    lm.upsert_session_summary(1, facts, "Resume textuel de la session.", 5, db_path=tmp_db)
    s = lm.get_session_summary(1, db_path=tmp_db)
    assert s["pedagogical_facts"]["niveau_estime"] == "intermediaire"
    assert s["text_summary"] == "Resume textuel de la session."
    assert s["turn_count"] == 5
    # Upsert
    lm.upsert_session_summary(1, {"niveau_estime": "avance"}, "Nouveau resume.", 8, db_path=tmp_db)
    s2 = lm.get_session_summary(1, db_path=tmp_db)
    assert s2["turn_count"] == 8
    assert s2["pedagogical_facts"]["niveau_estime"] == "avance"


def test_get_learner_context_aggregates(tmp_db):
    from apps.api.agent.memory import learner_model as lm

    _seed(tmp_db, n_competencies=2, n_sessions=1)
    lm.update_session_score(1, 1, 0.7, db_path=tmp_db)
    lm.record_method_outcome(1, "scaffold", success=True, db_path=tmp_db)
    lm.bump_topic("default_user", "variables", db_path=tmp_db)
    lm.upsert_session_summary(1, {"ok": True}, "Resume.", 3, db_path=tmp_db)

    ctx = lm.get_learner_context("default_user", session_id=1, db_path=tmp_db)
    assert len(ctx["competencies"]) == 2
    assert ctx["session_scores"][1]["score"] == 0.7
    assert ctx["best_method_by_competency"].get(1) == "scaffold"
    assert ctx["top_topics"][0]["topic"] == "variables"
    assert ctx["session_summary"]["turn_count"] == 3
