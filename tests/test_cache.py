"""Tests des caches memoire (TTL/LRU/invalidation) + integration crud/RAG."""
import time

from cachetools import TTLCache

from apps.api.services import cache


def test_get_set():
    cache.clear_all()
    assert cache.cache_get(cache.profile_cache, "u1") is None
    cache.cache_set(cache.profile_cache, "u1", {"domain": "maths"})
    assert cache.cache_get(cache.profile_cache, "u1") == {"domain": "maths"}


def test_ttl_expire():
    # Instance a TTL court pour ne pas ralentir la suite
    short = TTLCache(maxsize=4, ttl=0.2)
    cache.cache_set(short, "k", "v")
    assert cache.cache_get(short, "k") == "v"
    time.sleep(0.3)
    assert cache.cache_get(short, "k") is None


def test_invalidate_profile():
    cache.clear_all()
    cache.cache_set(cache.profile_cache, "u3", "v")
    cache.invalidate_profile("u3")
    assert cache.cache_get(cache.profile_cache, "u3") is None


def test_invalidate_competencies():
    cache.clear_all()
    cache.cache_set(cache.competency_cache, "maths", [1, 2])
    cache.cache_set(cache.competency_cache, "physique", [3])
    cache.invalidate_competencies("maths")
    assert cache.cache_get(cache.competency_cache, "maths") is None
    assert cache.cache_get(cache.competency_cache, "physique") == [3]
    cache.invalidate_competencies()  # tout
    assert cache.cache_get(cache.competency_cache, "physique") is None


def test_rag_cache_key_stable():
    k1 = cache.rag_key("quelle question ?", 3)
    k2 = cache.rag_key("quelle question ?", 3)
    k3 = cache.rag_key("autre question", 3)
    assert k1 == k2 and k1 != k3


# ─── Integration crud (profil + competences) ─────────────────────────────


def test_profile_cached_and_invalidated(tmp_db):
    from apps.api.db import crud

    cache.clear_all()
    p1 = crud.get_profile(user_id="cache_user", db_path=tmp_db)
    crud.get_profile(user_id="cache_user", db_path=tmp_db)
    key = f"cache_user|{tmp_db}"
    assert cache.cache_get(cache.profile_cache, key) is not None
    # ecriture → invalidation
    crud.update_profile(niveau_global="avance", user_id="cache_user", db_path=tmp_db)
    assert cache.cache_get(cache.profile_cache, key) is None
    p3 = crud.get_profile(user_id="cache_user", db_path=tmp_db)
    assert p3.get("niveau_global") == "avance"
    assert p1.get("user_id") == "cache_user"


def test_competencies_cached_and_invalidated(tmp_db):
    from apps.api.db import crud

    cache.clear_all()
    crud.get_competencies("maths", db_path=tmp_db)
    key = f"maths|{tmp_db}"
    assert cache.cache_get(cache.competency_cache, key) is not None
    crud.create_competency("maths", "Fractions", db_path=tmp_db)
    assert cache.cache_get(cache.competency_cache, key) is None
    c2 = crud.get_competencies("maths", db_path=tmp_db)
    assert any(c["nom"] == "Fractions" for c in c2)


# ─── Cache RAG ────────────────────────────────────────────────────────────


def test_rag_cache_hit():
    from apps.api.agent import nodes
    from apps.api.rag import retriever as rag_retriever

    calls = {"n": 0}

    class FakeRetriever:
        def invoke(self, q):
            calls["n"] += 1
            return []

    def fake_retrieve_semantic(retriever, question, top_k=3, threshold=0.0):
        calls["n"] += 1
        return [], 0.0, False

    # retrieve_semantic est importe DANS la fonction → patcher le module source
    orig = rag_retriever.retrieve_semantic
    rag_retriever.retrieve_semantic = fake_retrieve_semantic
    try:
        cache.clear_all()
        state = {
            "question": "sujet neutre sans indice factuel xyz",
            "rag_needed": True,
            "tool_transparency": [],
        }
        nodes.retrieval_node(state, FakeRetriever())
        nodes.retrieval_node(state, FakeRetriever())
        assert calls["n"] == 1  # 2e appel servi depuis le cache
    finally:
        rag_retriever.retrieve_semantic = orig
