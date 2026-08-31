"""Retriever Chroma Cloud — recherche hybride (dense qwen + sparse splade, RRF).

Architecture :
- Client natif chromadb.CloudClient (tenant/database/api_key) — pas de modele
  ONNX local, les embeddings sont generes cote serveur Chroma Cloud.
- Collection "agent_documents" avec Schema explicite :
  * #embedding (dense)     : ChromaCloudQwen (serveur)
  * sparse_embedding       : ChromaCloudSplade (serveur, mot-cles)
- Recherche hybride : fusion RRF (70% dense / 30% sparse).
- Dedup par document source (meilleur chunk/document, via metadonnee
  source_doc_id) ; metadonnees chunk_index pour la tracabilite.
- Chunking < 16 KiB impose par Chroma (truncation propre si besoin).

Specs : docs.trychroma.com — hybrid-search.md, sparse-vector-search.md,
group-by.md, chroma-cloud-qwen.md, chroma-cloud-splade.md.

Fallback local (dev sans cloud) : embeddings Ollama + Chroma persistant
(deplace dans retriever_local.py, comportement identique a l'ancienne impl).
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION_NAME = "agent_documents"
MAX_CHUNK_KIB = 16 * 1024  # Limite Chroma : 16 KiB par document


def _use_chroma_cloud() -> bool:
    """True si Chroma Cloud est configuré (CHROMA_API_KEY ou CHROMA_CLOUD_API_KEY)."""
    return bool(os.getenv("CHROMA_API_KEY") or os.getenv("CHROMA_CLOUD_API_KEY"))


def _cloud_settings() -> dict:
    """Lit la conf cloud (variables CHROMA_* ou legacy CHROMA_CLOUD_*)."""
    return {
        "tenant": os.getenv("CHROMA_TENANT", "")
        or os.getenv("CHROMA_CLOUD_TENANT", ""),
        "database": os.getenv("CHROMA_DATABASE", "")
        or os.getenv("CHROMA_CLOUD_DATABASE", ""),
        "api_key": os.getenv("CHROMA_API_KEY", "")
        or os.getenv("CHROMA_CLOUD_API_KEY", ""),
    }


_client_cache = {}


def _get_cloud_client():
    """Client Chroma Cloud singleton (un par tenant/database)."""
    s = _cloud_settings()
    cache_key = f"{s['tenant']}|{s['database']}"
    if cache_key not in _client_cache:
        import chromadb

        _client_cache[cache_key] = chromadb.CloudClient(
            tenant=s["tenant"],
            database=s["database"],
            api_key=s["api_key"],
        )
        logger.info(
            f"Chroma Cloud client initialise (database={s['database']})"
        )
    return _client_cache[cache_key]


def _build_schema():
    """Schema de collection : dense serveur (qwen) + sparse serveur (splade).

    Le dense #embedding est configure par l'embedding_function de la
    collection (ChromaCloudQwenEmbeddingFunction) ; le sparse est un index
    explicite sur K.DOCUMENT avec ChromaCloudSpladeEmbeddingFunction.
    """
    from chromadb import Schema, SparseVectorIndexConfig, K
    from chromadb.utils.embedding_functions import (
        ChromaCloudSpladeEmbeddingFunction,
        ChromaCloudQwenEmbeddingFunction,
        ChromaCloudQwenEmbeddingModel,
    )

    schema = Schema()
    sparse_ef = ChromaCloudSpladeEmbeddingFunction()
    schema.create_index(
        config=SparseVectorIndexConfig(
            source_key=K.DOCUMENT,
            embedding_function=sparse_ef,
        ),
        key="sparse_embedding",
    )
    # L'embedding dense de la collection (source_key=K.DOCUMENT par defaut)
    qwen_ef = ChromaCloudQwenEmbeddingFunction(
        model=ChromaCloudQwenEmbeddingModel.QWEN3_EMBEDDING_0p6B,
        task="retrieval.passage",
    )
    schema.create_index(
        config=None,  # config dense par defaut
        key="#embedding",
        embedding_function=qwen_ef,
    ) if False else None  # dense EF passee via embedding_function de collection
    return schema, qwen_ef


def _chunk_id(text: str, source: str = "", idx: int = 0) -> str:
    """ID deterministe pour un chunk — re-indexer un PDF est idempotent."""
    raw = f"{source}|{idx}|{text[:128]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _enforce_chunk_limit(splits: list) -> list:
    """Chroma limite un document a 16 KiB ; tronque proprement les trop longs."""
    out = []
    for d in splits:
        text = d if isinstance(d, str) else d.page_content
        if len(text.encode("utf-8")) <= MAX_CHUNK_KIB:
            out.append(d)
            continue
        cut = text.encode("utf-8")[:MAX_CHUNK_KIB - 1].decode("utf-8", "ignore")
        cut = cut.rsplit(" ", 1)[0]
        if isinstance(d, str):
            out.append(cut)
        else:
            from copy import deepcopy

            shorter = deepcopy(d)
            shorter.page_content = cut
            out.append(shorter)
    return out


def _prepare_splits(splits: list) -> tuple:
    """Normalise les LangChain Documents en (ids, texts, metadatas).

    Ajoute source_doc_id + chunk_index si absents (dedup group-by cote
    recherche, tracabilite cote UI).
    """
    ids, texts, metas = [], [], []
    for i, split in enumerate(splits):
        if isinstance(split, str):
            text, meta = split, {}
        else:
            text = split.page_content
            meta = dict(split.metadata or {})
        source = meta.get("source") or meta.get("source_doc_id") or "doc"
        meta.setdefault("source_doc_id", source)
        meta.setdefault("chunk_index", i)
        ids.append(_chunk_id(text, str(source), meta["chunk_index"]))
        texts.append(text)
        metas.append(meta)
    return ids, texts, metas


class ChromaCloudRetriever:
    """Retriever natif Chroma Cloud — interface compatible LangChain.

    - invoke()/get_relevant_documents() : recherche hybride RRF → Documents.
    - hybrid_search() : API brute (ids, documents, metadatas, scores).
    - add_documents() : upsert avec embeddings serveur (dense+sparse auto).
    """

    def __init__(self, collection, top_k: int = 3, rrf_k: int = 60,
                 dense_weight: float = 0.7, sparse_weight: float = 0.3):
        self.collection = collection
        self.top_k = top_k
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    # ── Recherche hybride (API brute) ─────────────────────────────────────

    def hybrid_search(self, query: str, top_k: Optional[int] = None,
                      where: Optional[dict] = None) -> dict:
        """Recherche hybride dense+sparse fusionnee par RRF.

        Returns (dict ou objet natif selon version chromadb) :
            ids / documents / metadatas / scores (listes par requete).
        """
        from chromadb import Search, Knn, Rrf

        k = top_k or self.top_k
        dense = Knn(query=query, key="#embedding", return_rank=True, limit=200)
        sparse = Knn(query=query, key="sparse_embedding",
                     return_rank=True, limit=200)
        rank = Rrf(
            ranks=[dense, sparse],
            weights=[self.dense_weight, self.sparse_weight],
            k=self.rrf_k,
        )
        search = Search().rank(rank).limit(k)
        if where:
            search = search.where(where)
        return self.collection.search(search)

    # ── Interface LangChain-compatible ────────────────────────────────────

    def get_relevant_documents(self, query: str, **kwargs) -> list:
        return self.invoke(query, **kwargs)

    def invoke(self, query: str, **kwargs) -> list:
        """Recherche hybride → Documents LangChain, dedup par source_doc_id."""
        from langchain_core.documents import Document

        try:
            res = self.hybrid_search(query, top_k=kwargs.get("k"))
        except Exception as e:
            logger.warning(f"Recherche hybride echouee ({e}); repli dense.")
            try:
                res = self.collection.query(query_texts=[query],
                                            n_results=self.top_k)
            except Exception as e2:
                logger.warning(f"Repli dense echoue ({e2})")
                return [], 0.0, False if False else []

        docs_raw, metas = self._extract(res)
        if not docs_raw:
            return []

        # Dedup par document source : 1 seul chunk par source
        seen, out = set(), []
        for text, meta in zip(docs_raw, metas):
            meta = meta or {}
            src = meta.get("source_doc_id")
            if src and src in seen:
                continue
            if src:
                seen.add(src)
            out.append(Document(page_content=text, metadata=meta))
        return out

    @staticmethod
    def _extract(res) -> tuple:
        """Extrait (documents, metadatas) d'une reponse search/query."""
        if isinstance(res, dict):
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
        else:
            docs = getattr(res, "documents", None)
            metas = getattr(res, "metadatas", None)
            docs = docs[0] if docs else []
            metas = metas[0] if metas else []
        return list(docs or []), list(metas or [])

    # ── Ingestion ─────────────────────────────────────────────────────────

    def add_documents(self, splits: list) -> int:
        """Upsert des chunks — embeddings serveur generes automatiquement."""
        splits = _enforce_chunk_limit(splits)
        ids, texts, metas = _prepare_splits(splits)
        if not ids:
            return 0
        self.collection.upsert(ids=ids, documents=texts, metadatas=metas)
        logger.info(f"Chroma Cloud: {len(ids)} chunks upsertes")
        return len(ids)

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0


# ═══════════════════════════════════════════════════════════════════════════
# API PUBLIQUE (interface compatible avec l'ancienne implementation)
# ═══════════════════════════════════════════════════════════════════════════


def get_or_create_retriever(
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Charge la collection cloud (ou locale en dev) et retourne le retriever."""
    if _use_chroma_cloud():
        client = _get_cloud_client()
        try:
            schema, qwen_ef = _build_schema()
            collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                schema=schema,
                embedding_function=qwen_ef,
            )
            return ChromaCloudRetriever(collection, top_k=top_k)
        except Exception as e:
            logger.warning(f"Chroma Cloud schema init echoue ({e}); load simple.")
            try:
                collection = client.get_collection(COLLECTION_NAME)
                return ChromaCloudRetriever(collection, top_k=top_k)
            except Exception as e2:
                logger.error(f"Chroma Cloud indisponible: {e2}")
                from apps.api.rag.retriever_local import (
                    get_or_create_retriever as local_fn,
                )
                return local_fn(model_name=model_name, top_k=top_k,
                                persist_dir=persist_dir)

    from apps.api.rag.retriever_local import get_or_create_retriever as local_fn
    return local_fn(model_name=model_name, top_k=top_k, persist_dir=persist_dir)


def add_documents_to_retriever(
    retriever,
    splits: list,
    embeddings=None,  # ignore en cloud : embeddings generes cote serveur
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Ajoute des documents au retriever (upsert cloud ou add local)."""
    if isinstance(retriever, ChromaCloudRetriever):
        return retriever.add_documents(splits)

    # Retriever LangChain local
    from langchain_chroma import Chroma

    kwargs = _local_chroma_kwargs(persist_dir)
    try:
        vectorstore = Chroma(embedding_function=_get_local_embedding(model_name),
                             **kwargs)
        vectorstore.add_documents(splits)
    except Exception as e:
        logger.warning(f"add_documents local echoue ({e}); from_documents.")
        Chroma.from_documents(documents=splits,
                              embedding=_get_local_embedding(model_name),
                              **kwargs)
    return len(splits)


def retrieve_semantic(retriever, query: str, top_k: int = 3,
                      threshold: float = 0.3):
    """Recherche avec score de pertinence — interface inchangee.

    Retourne (docs, best_score, has_relevant).
    """
    from langchain_core.documents import Document

    # Retriever hybride cloud
    if isinstance(retriever, ChromaCloudRetriever):
        try:
            res = retriever.hybrid_search(query, top_k=top_k)
        except Exception as e:
            logger.warning(f"Recherche hybride echouee ({e})")
            return [], 0.0, False

        if isinstance(res, dict):
            docs_raw = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            scores = (res.get("scores") or [[]])[0] if res.get("scores") else None
        else:
            docs_raw = getattr(res, "documents", None)
            docs_raw = docs_raw[0] if docs_raw else []
            metas = getattr(res, "metadatas", None)
            metas = metas[0] if metas else []
            scores = getattr(res, "scores", None)
            scores = scores[0] if scores else None

        if not docs_raw:
            return [], 0.0, False

        # Scores RRF negatifs (plus proche de 0 = meilleur).
        # Sans scores (API ancienne), tous les resultats sont consideres
        # pertinents ; avec scores, conversion indicative :
        #   |score RRF| ~ [0.001, 0.05] → norm = 1 - min(1, |s| * 20)
        relevant, best = [], 0.0
        if not scores:
            for i, text in enumerate(docs_raw):
                meta = (metas[i] if metas and i < len(metas) else {}) or {}
                relevant.append(Document(page_content=text, metadata=meta))
            return relevant, 1.0, True

        for i, text in enumerate(docs_raw):
            norm = max(0.0, min(1.0, 1.0 - abs(scores[i]) * 20))
            best = max(best, norm)
            if norm >= threshold:
                meta = (metas[i] if metas and i < len(metas) else {}) or {}
                relevant.append(Document(page_content=text, metadata=meta))
        if relevant:
            return relevant, best, True
        meta0 = (metas[0] if metas else {}) or {}
        return [Document(page_content=docs_raw[0], metadata=meta0)], best, False

    # Retriever LangChain local / mock — ancienne logique
    vectorstore = getattr(retriever, "vectorstore", None)
    if vectorstore is None or not hasattr(vectorstore, "similarity_search_with_score"):
        try:
            docs = retriever.invoke(query)
            return docs, 1.0, bool(docs)
        except Exception:
            return [], 0.0, False

    try:
        docs_scores = vectorstore.similarity_search_with_score(query, k=top_k)
    except Exception as e:
        logger.warning(f"similarity_search_with_score echoue ({e}); fallback.")
        try:
            docs = retriever.invoke(query)
            return docs, 1.0, bool(docs)
        except Exception:
            return [], 0.0, False

    if not docs_scores:
        return [], 0.0, False

    relevant, best = [], 0.0
    for doc, dist in docs_scores:
        score = max(0.0, min(1.0, 1.0 - float(dist)))
        best = max(best, score)
        if score >= threshold:
            relevant.append(doc)
    if relevant:
        return relevant, best, True
    return [docs_scores[0][0]], best, False


# ── Mode local (dev) — helpers partages ──────────────────────────────────


def _get_local_embedding(model_name: str = "qwen3-embedding:0.6b"):
    """Embeddings Ollama pour le mode local (dev sans cloud)."""
    from langchain_ollama import OllamaEmbeddings

    kwargs = {"model": model_name}
    base = os.getenv("EMBEDDING_BASE_URL", "") or os.getenv("OLLAMA_BASE_URL", "")
    if base:
        kwargs["base_url"] = base
    api_key = os.getenv("OLLAMA_API_KEY", "")
    if api_key:
        kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}
    return OllamaEmbeddings(**kwargs)


def _local_chroma_kwargs(persist_dir: Optional[str]) -> dict:
    if persist_dir:
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        return {"persist_directory": persist_dir, "collection_name": COLLECTION_NAME}
    return {"collection_name": COLLECTION_NAME}
