"""Retriever ChromaDB — création, chargement, ajout incrémental.

Port de V2 rag/retriever.py pour FastAPI V3.
L'embedding reste TOUJOURS LOCAL même si OLLAMA_BASE_URL est distant.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _get_embedding(model_name: str = "qwen3-embedding:0.6b"):
    """Instancie les embeddings Ollama (toujours local)."""
    from langchain_ollama import OllamaEmbeddings

    kwargs = {"model": model_name}
    embedding_base = os.getenv("EMBEDDING_BASE_URL", "")
    if embedding_base:
        kwargs["base_url"] = embedding_base
    return OllamaEmbeddings(**kwargs)


def create_retriever(
    splits: list,
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Crée un retriever ChromaDB à partir de documents chunkés."""
    from langchain_chroma import Chroma

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


def get_or_create_retriever(
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Charge un retriever existant, ou en crée un vide."""
    from langchain_chroma import Chroma

    embedding = _get_embedding(model_name)

    if persist_dir and Path(persist_dir).exists():
        vectorstore = Chroma(
            persist_directory=persist_dir,
            embedding_function=embedding,
        )
    else:
        from langchain_core.documents import Document

        if persist_dir:
            Path(persist_dir).mkdir(parents=True, exist_ok=True)
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


def add_documents_to_retriever(
    splits: list,
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Ajoute des documents au vectorstore existant."""
    from langchain_chroma import Chroma

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
