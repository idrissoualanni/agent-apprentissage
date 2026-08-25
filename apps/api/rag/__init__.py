"""Module RAG — ingestion, retriever, embeddings."""

from apps.api.rag.retriever import (
    get_or_create_retriever,
    add_documents_to_retriever,
    create_retriever,
)
from apps.api.rag.ingestion import ingest_pdf

__all__ = [
    "get_or_create_retriever",
    "add_documents_to_retriever",
    "create_retriever",
    "ingest_pdf",
]
