"""Tests Phase 6 — revision planner (repetition espacee Leitner)."""

import sqlite3
from datetime import datetime, timedelta


def _seed_mastery(db_path, competency_id=1, leitner_box=1, next_review_offset_days=-1):
    """Cree une competence + mastery avec une date de revision passee/future."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO competency (id, domain, nom) VALUES (?, 'Python', 'variables')",
        (competency_id,),
    )
    next_dt = datetime.now() + timedelta(days=next_review_offset_days)
    next_iso = next_dt.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO mastery (competency_id, score, leitner_box, status, next_review_at) "
        "VALUES (?, 0.6, ?, 'learning', ?)",
        (competency_id, leitner_box, next_iso),
    )
    conn.commit()
    conn.close()


def test_compute_next_review_intervals():
    from apps.api.agent.memory.revision_planner import compute_next_review, LEITNER_INTERVALS_DAYS

    base = datetime(2026, 1, 1)
    for box, days in LEITNER_INTERVALS_DAYS.items():
        result = compute_next_review(box, from_dt=base)
        assert result == base + timedelta(days=days), f"box {box}"


def test_schedule_review_updates_db(tmp_db):
    from apps.api.agent.memory import revision_planner as rp
    from apps.api.db import crud

    _seed_mastery(tmp_db, next_review_offset_days=10)
    iso = rp.schedule_review(1, leitner_box=3, db_path=tmp_db)
    assert iso is not None
    m = crud.get_mastery(1, db_path=tmp_db)
    assert m["next_review_at"] == iso


def test_get_due_reviews_returns_past(tmp_db):
    from apps.api.agent.memory import revision_planner as rp

    # Revision due (date passee)
    _seed_mastery(tmp_db, competency_id=1, next_review_offset_days=-1)
    due = rp.get_due_reviews(db_path=tmp_db)
    assert len(due) == 1
    assert due[0]["competency_id"] == 1


def test_get_due_reviews_excludes_future(tmp_db):
    from apps.api.agent.memory import revision_planner as rp

    # Revision future (pas due)
    _seed_mastery(tmp_db, competency_id=1, next_review_offset_days=5)
    due = rp.get_due_reviews(db_path=tmp_db)
    assert len(due) == 0


def test_get_revision_calendar(tmp_db):
    from apps.api.agent.memory import revision_planner as rp

    _seed_mastery(tmp_db, competency_id=1, next_review_offset_days=2)
    cal = rp.get_revision_calendar(db_path=tmp_db)
    assert len(cal) == 1
    assert cal[0]["nom"] == "variables"
    assert cal[0]["next_review_at"] is not None
