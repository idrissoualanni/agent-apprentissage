"""Retriever ChromaDB — création, chargement, ajout incrémental.

Note importante : l'embedding reste TOUJOURS LOCAL, même si OLLAMA_BASE_URL
pointe vers Ollama Cloud. Raison : les modèles d'embedding ne sont pas
toujours disponibles sur Ollama Cloud, et la latence serait excessive.

Si tu veux quand même utiliser un embedding cloud, force EMBEDDING_BASE_URL
dans le .env vers un serveur qui heberge le modele d'embedding.
"""

import os
from pathlib import Path
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
import config


def _get_embedding(model_name: str = "qwen3-embedding:0.6b"):
    """Instancie les embeddings Ollama (toujours local).

    Par defaut, on ignore OLLAMA_BASE_URL pour les embeddings (qui pointe
    vers le cloud utilise pour le LLM). On lit ``EMBEDDING_BASE_URL`` si
    defini dans l'env pour forcer un serveur d'embedding specifique.
    """
    kwargs = {"model": model_name}

    embedding_base = os.getenv("EMBEDDING_BASE_URL", "")
    if embedding_base:
        kwargs["base_url"] = embedding_base

    return OllamaEmbeddings(**kwargs)


def create_retriever(splits: list, model_name: str = "qwen3-embedding:0.6b",
                     top_k: int = 3, persist_dir: str = None):
    """Crée un retriever ChromaDB à partir de documents chunkés."""
    embedding = _get_embedding(model_name)

    if persist_dir:
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embedding,
            persist_directory=persist_dir,
        )
    else:
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embedding,
        )

    return vectorstore.as_retriever(search_kwargs={"k": top_k})


def get_or_create_retriever(model_name: str = "qwen3-embedding:0.6b",
                            top_k: int = 3, persist_dir: str = None):
    """Charge un retriever existant, ou en crée un vide si le dossier n'existe pas."""
    embedding = _get_embedding(model_name)

    if persist_dir and Path(persist_dir).exists():
        vectorstore = Chroma(
            persist_directory=persist_dir,
            embedding_function=embedding,
        )
    else:
        # Créer un vectorstore vide avec un document placeholder
        from langchain_core.documents import Document
        vectorstore = Chroma.from_documents(
            documents=[Document(page_content="placeholder", metadata={"source": "init"})],
            embedding=embedding,
            persist_directory=persist_dir,
        )
        if persist_dir:
            ids = vectorstore.get()["ids"]
            if ids:
                vectorstore.delete(ids=ids[:1])

    return vectorstore.as_retriever(search_kwargs={"k": top_k})


def add_documents_to_retriever(splits: list, model_name: str = "qwen3-embedding:0.6b",
                               top_k: int = 3, persist_dir: str = None):
    """Ajoute des documents au vectorstore existant (ou en crée un nouveau)."""
    embedding = _get_embedding(model_name)

    if persist_dir and Path(persist_dir).exists():
        vectorstore = Chroma(
            persist_directory=persist_dir,
            embedding_function=embedding,
        )
        vectorstore.add_documents(splits)
    else:
        if persist_dir:
            Path(persist_dir).mkdir(parents=True, exist_ok=True)
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embedding,
            persist_directory=persist_dir,
        )

    return vectorstore.as_retriever(search_kwargs={"k": top_k})
