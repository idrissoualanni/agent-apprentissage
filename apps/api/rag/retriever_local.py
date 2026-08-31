"""Retriever local (dev) — ChromaDB persistant + embeddings Ollama.

C'est l'ancienne implementation de retriever.py, conservee comme fallback
quand Chroma Cloud n'est pas configure (dev locale sans cloud).
En production, apps.api.rag.retriever utilise Chroma Cloud (hybride RRF).
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION_NAME = "agent_documents"


def _get_local_embedding(model_name: str = "qwen3-embedding:0.6b"):
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


def get_or_create_retriever(
    model_name: str = "qwen3-embedding:0.6b",
    top_k: int = 3,
    persist_dir: Optional[str] = None,
):
    """Charge/cree un retriever Chroma local avec embeddings Ollama."""
    from langchain_chroma import Chroma

    embedding = _get_local_embedding(model_name)
    kwargs = _local_chroma_kwargs(persist_dir)

    vectorstore = Chroma(embedding_function=embedding, **kwargs)
    return vectorstore.as_retriever(search_kwargs={"k": top_k})
