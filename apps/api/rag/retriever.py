"""Retriever ChromaDB — création, chargement, ajout incrémental.

Port de V2 rag/retriever.py pour FastAPI V3.
Supporte deux modes :
- Local : ChromaDB persistant local + embeddings Ollama locaux (dev).
- Cloud : Chroma Cloud + embeddings Ollama Cloud (production).

Le mode cloud est activé si CHROMA_CLOUD_API_KEY est définie.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION_NAME = "agent_apprentissage"


def _use_chroma_cloud() -> bool:
    """True si Chroma Cloud est configuré."""
    return bool(os.getenv("CHROMA_CLOUD_API_KEY"))


def _get_embedding(model_name: str = "qwen3-embedding:0.6b"):
    """Instancie les embeddings Ollama (cloud par defaut, local en fallback).

    En production, OLLAMA_BASE_URL pointe vers Ollama Cloud : les embeddings
    sont donc cloud. EMBEDDING_BASE_URL peut surcharger si besoin.
    """
    from langchain_ollama import OllamaEmbeddings

    kwargs = {"model": model_name}
    # Priorite : EMBEDDING_BASE_URL > OLLAMA_BASE_URL (cloud)
    embedding_base = os.getenv("EMBEDDING_BASE_URL", "") or os.getenv("OLLAMA_BASE_URL", "")
    if embedding_base:
        kwargs["base_url"] = embedding_base
    # Si une cle API Ollama est presente, la transmettre (Ollama Cloud).
    api_key = os.getenv("OLLAMA_API_KEY", "")
    if api_key:
        kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}
    return OllamaEmbeddings(**kwargs)


def _chroma_kwargs(persist_dir: Optional[str]) -> dict:
    """Retourne les kwargs pour instancier Chroma (cloud ou local)."""
    if _use_chroma_cloud():
        import chromadb

        client = chromadb.CloudClient(
            tenant=os.getenv("CHROMA_CLOUD_TENANT", ""),
            database=os.getenv("CHROMA_CLOUD_DATABASE", "default_database"),
            api_key=os.getenv("CHROMA_CLOUD_API_KEY", ""),
        )
        return {"client": client, "collection_name": COLLECTION_NAME}
    # Mode local
    if persist_dir:
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        return {"persist_directory": persist_dir, "collection_name": COLLECTION_NAME}
    return {"collection_name": COLLECTION_NAME}


def create_retriever(
    splits: list,
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Crée un retriever ChromaDB à partir de documents chunkés (cloud ou local)."""
    from langchain_chroma import Chroma

    embedding = _get_embedding(model_name)
    kwargs = _chroma_kwargs(persist_dir)

    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embedding,
        **kwargs,
    )

    return vectorstore.as_retriever(search_kwargs={"k": top_k})


def get_or_create_retriever(
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Charge un retriever existant, ou en crée un vide (cloud ou local)."""
    from langchain_chroma import Chroma

    embedding = _get_embedding(model_name)
    kwargs = _chroma_kwargs(persist_dir)

    # En mode cloud, on tente de charger la collection existante.
    if _use_chroma_cloud():
        try:
            vectorstore = Chroma(
                embedding_function=embedding,
                **kwargs,
            )
            return vectorstore.as_retriever(search_kwargs={"k": top_k})
        except Exception as e:
            logger.warning(f"Chroma Cloud load échoué ({e}); création d'une collection vide.")
            from langchain_core.documents import Document
            vectorstore = Chroma.from_documents(
                documents=[Document(page_content="placeholder", metadata={"source": "init"})],
                embedding=embedding,
                **kwargs,
            )
            ids = vectorstore.get()["ids"]
            if ids:
                vectorstore.delete(ids=ids[:1])
            return vectorstore.as_retriever(search_kwargs={"k": top_k})

    # Mode local
    if persist_dir and Path(persist_dir).exists():
        vectorstore = Chroma(
            embedding_function=embedding,
            **kwargs,
        )
    else:
        from langchain_core.documents import Document

        vectorstore = Chroma.from_documents(
            documents=[Document(page_content="placeholder", metadata={"source": "init"})],
            embedding=embedding,
            **kwargs,
        )
        ids = vectorstore.get()["ids"]
        if ids:
            vectorstore.delete(ids=ids[:1])

    return vectorstore.as_retriever(search_kwargs={"k": top_k})


def retrieve_semantic(retriever, query: str, top_k: int = 3, threshold: float = 0.3):
    """Correctif 5 : recherche sémantique avec score de pertinence.

    Retourne (docs, best_score, has_relevant) où :
    - docs : liste de Documents au-dessus du seuil (ou tous si aucun ne passe)
    - best_score : meilleur score de similarité trouvé
    - has_relevant : True si au moins un chunk dépasse le seuil

    Compatible avec un vrai retriever Chroma ou un mock (fallback gracieux).
    """
    # Accéder au vectorstore sous-jacent si possible
    vectorstore = getattr(retriever, "vectorstore", None)
    if vectorstore is None or not hasattr(vectorstore, "similarity_search_with_score"):
        # Fallback : retriever simple (mock ou sans score)
        try:
            docs = retriever.invoke(query)
            return docs, 1.0, bool(docs)
        except Exception:
            return [], 0.0, False

    try:
        docs_scores = vectorstore.similarity_search_with_score(query, k=top_k)
    except Exception as e:
        logger.warning(f"similarity_search_with_score échoué ({e}); fallback invoke.")
        try:
            docs = retriever.invoke(query)
            return docs, 1.0, bool(docs)
        except Exception:
            return [], 0.0, False

    if not docs_scores:
        return [], 0.0, False

    # Chroma retourne une distance (plus petite = plus proche).
    # On normalise : score de pertinence = 1 - distance (borné à [0,1]).
    relevant = []
    best_score = 0.0
    for doc, dist in docs_scores:
        score = max(0.0, min(1.0, 1.0 - float(dist)))
        best_score = max(best_score, score)
        if score >= threshold:
            relevant.append(doc)

    if relevant:
        return relevant, best_score, True
    # Aucun chunk au-dessus du seuil : retourner le meilleur pour inspection
    return [docs_scores[0][0]], best_score, False


def add_documents_to_retriever(
    splits: list,
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Ajoute des documents au vectorstore existant (cloud ou local)."""
    from langchain_chroma import Chroma

    embedding = _get_embedding(model_name)
    kwargs = _chroma_kwargs(persist_dir)

    # En mode cloud ou si le persist_dir existe, on charge puis on ajoute.
    if _use_chroma_cloud() or (persist_dir and Path(persist_dir).exists()):
        try:
            vectorstore = Chroma(
                embedding_function=embedding,
                **kwargs,
            )
            vectorstore.add_documents(splits)
        except Exception as e:
            logger.warning(f"add_documents load échoué ({e}); création depuis splits.")
            vectorstore = Chroma.from_documents(
                documents=splits,
                embedding=embedding,
                **kwargs,
            )
    else:
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embedding,
            **kwargs,
        )

    return vectorstore.as_retriever(search_kwargs={"k": top_k})
