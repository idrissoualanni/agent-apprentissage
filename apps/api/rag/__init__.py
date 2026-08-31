"""Module RAG — ingestion, retriever, embeddings."""

from apps.api.rag.retriever import (
    get_or_create_retriever,
    add_documents_to_retriever,
    retrieve_semantic,
    ChromaCloudRetriever,
)
from apps.api.rag.ingestion import load_pdf, chunk_documents

__all__ = [
    "get_or_create_retriever",
    "add_documents_to_retriever",
    "retrieve_semantic",
    "ChromaCloudRetriever",
    "load_pdf",
    "chunk_documents",
]
