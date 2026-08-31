"""Tests du retriever Chroma Cloud natif (hybride RRF) — sans reseau.

La collection est mockee : les tests valident la logique (schema, upsert,
recherche hybride, dedup par source, seuil) sans appeler l'API Chroma.
"""
import pytest
from unittest.mock import MagicMock, patch

from apps.api.rag import retriever as r


# ── Construction du retriever cloud ──────────────────────────────────────


class FakeSearchResult:
    """Reponse de collection.search() (API hybride)."""

    def __init__(self, docs, metas):
        self.documents = [docs]
        self.metadatas = [metas]


def _fake_collection():
    col = MagicMock()
    col.search.return_value = FakeSearchResult(
        ["La photosynthese transforme la lumiere.",
         "Chlore = vert. Les plantes font la photosynthese.",
         "Respiration cellulaire : autre sujet."],
        [{"source_doc_id": "bio.pdf", "chunk_index": 0},
         {"source_doc_id": "bio.pdf", "chunk_index": 1},
         {"source_doc_id": "resp.pdf", "chunk_index": 0}],
    )
    return col


def test_cloud_settings_from_new_and_legacy_vars(monkeypatch):
    monkeypatch.setenv("CHROMA_API_KEY", "ck-123")
    monkeypatch.setenv("CHROMA_TENANT", "t1")
    monkeypatch.setenv("CHROMA_DATABASE", "agent")
    s = r._cloud_settings()
    assert s["api_key"] == "ck-123"
    assert s["database"] == "agent"

    monkeypatch.delenv("CHROMA_API_KEY")
    monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "ck-legacy")
    s = r._cloud_settings()
    assert s["api_key"] == "ck-legacy"


def test_use_cloud_detection(monkeypatch):
    monkeypatch.delenv("CHROMA_API_KEY", raising=False)
    monkeypatch.delenv("CHROMA_CLOUD_API_KEY", raising=False)
    assert r._use_chroma_cloud() is False
    monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "x")
    assert r._use_chroma_cloud() is True


# ── Chunking 16 KiB ──────────────────────────────────────────────────────


def test_chunk_limit_truncates():
    big = "mot " * 5000  # ~20 KiB
    out = r._enforce_chunk_limit([big])
    assert len(out) == 1
    assert len(out[0].encode("utf-8")) <= 16 * 1024


def test_chunk_limit_keeps_small():
    small = "petit texte"
    out = r._enforce_chunk_limit([small])
    assert len(out) == 1
    assert out[0] == small


# ── Preparation des splits (ids deterministes, metadatas) ────────────────


def test_prepare_splits_adds_source_and_index():
    from langchain_core.documents import Document

    splits = [
        Document(page_content="a", metadata={"source": "maths.pdf"}),
        Document(page_content="b", metadata={"source": "maths.pdf"}),
    ]
    ids, texts, metas = r._prepare_splits(splits)
    assert len(ids) == 2
    assert metas[0]["source_doc_id"] == "maths.pdf"
    assert metas[0]["chunk_index"] == 0
    assert metas[1]["chunk_index"] == 1
    # IDs deterministes
    ids2, _, _ = r._prepare_splits(splits)
    assert ids == ids2


def test_prepare_splits_plain_strings():
    ids, texts, metas = r._prepare_splits(["texte seul"])
    assert ids and texts == ["texte seul"]
    assert metas[0]["source_doc_id"] == "doc"


# ── Recherche hybride + dedup ────────────────────────────────────────────


def test_invoke_dedups_by_source_doc():
    retriever = r.ChromaCloudRetriever(_fake_collection(), top_k=3)
    docs = retriever.invoke("photosynthese")
    assert len(docs) == 2  # bio.pdf (2 chunks → 1) + resp.pdf
    sources = {d.metadata["source_doc_id"] for d in docs}
    assert sources == {"bio.pdf", "resp.pdf"}


def test_hybrid_search_builds_rrf():
    col = _fake_collection()
    retriever = r.ChromaCloudRetriever(col, top_k=3)
    retriever.hybrid_search("qu est ce que la photosynthese")
    assert col.search.called
    # L'objet Search passe au mock contient un rank RRF
    search_obj = col.search.call_args[0][0]
    assert search_obj is not None


def test_retrieve_semantic_cloud_paths():
    retriever = r.ChromaCloudRetriever(_fake_collection(), top_k=3)
    # search renvoie 3 docs sans scores → norm par defaut 0.5 >= seuil 0.3
    docs, best, has = r.retrieve_semantic(retriever, "photosynthese",
                                          top_k=3, threshold=0.3)
    assert has is True
    assert best > 0
    assert len(docs) >= 1


def test_retrieve_semantic_cloud_no_results():
    col = MagicMock()
    col.search.return_value = FakeSearchResult([], [])
    retriever = r.ChromaCloudRetriever(col, top_k=3)
    docs, best, has = r.retrieve_semantic(retriever, "x")
    assert docs == []
    assert has is False


def test_retrieve_semantic_cloud_fallback_on_error():
    col = MagicMock()
    col.search.side_effect = RuntimeError("cloud down")
    retriever = r.ChromaCloudRetriever(col, top_k=3)
    docs, best, has = r.retrieve_semantic(retriever, "x")
    assert docs == []
    assert has is False


def test_retrieve_semantic_mock_retriever():
    """Retriever quelconque (mock des tests existants) — compatibilite."""
    from langchain_core.documents import Document

    class SimpleRetriever:
        vectorstore = None  # force le chemin invoke()

        def invoke(self, q):
            return [Document(page_content="ok")]

    fake = SimpleRetriever()
    docs, best, has = r.retrieve_semantic(fake, "q")
    assert has is True and docs[0].page_content == "ok"


def test_add_documents_upserts_with_ids():
    from langchain_core.documents import Document

    col = MagicMock()
    retriever = r.ChromaCloudRetriever(col, top_k=3)
    n = retriever.add_documents([
        Document(page_content="chunk 1", metadata={"source": "a.pdf"}),
        Document(page_content="chunk 2", metadata={"source": "a.pdf"}),
    ])
    assert n == 2
    assert col.upsert.called
    kw = col.upsert.call_args.kwargs
    assert len(kw["ids"]) == 2
    assert kw["metadatas"][0]["source_doc_id"] == "a.pdf"
    assert "chunk_index" in kw["metadatas"][0]


# ── get_or_create_retriever : route cloud vs local ────────────────────────


def test_get_or_create_routes_to_cloud(monkeypatch):
    monkeypatch.setenv("CHROMA_API_KEY", "ck-x")
    monkeypatch.setenv("CHROMA_TENANT", "t")
    monkeypatch.setenv("CHROMA_DATABASE", "agent")

    with patch.object(r, "_get_cloud_client") as gcc:
        gcc.return_value.get_or_create_collection.return_value = _fake_collection()
        retriever = r.get_or_create_retriever(top_k=3)
    assert isinstance(retriever, r.ChromaCloudRetriever)


def test_get_or_create_routes_to_local_when_no_cloud(monkeypatch):
    import importlib

    monkeypatch.delenv("CHROMA_API_KEY", raising=False)
    monkeypatch.delenv("CHROMA_CLOUD_API_KEY", raising=False)
    import apps.api.rag.retriever_local as rl

    called = {}
    orig = rl.get_or_create_retriever
    rl.get_or_create_retriever = lambda **kw: called.update(kw) or "local"
    try:
        out = r.get_or_create_retriever(model_name="m", top_k=5,
                                        persist_dir="d")
        assert out == "local"
        assert called["top_k"] == 5
    finally:
        rl.get_or_create_retriever = orig
