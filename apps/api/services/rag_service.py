"""Service RAG — ingestion de documents et gestion du retriever."""

import logging
from pathlib import Path
from typing import Optional

from apps.api.rag import ingestion, retriever as retriever_mod
from apps.api.db import crud
import apps.api.config as config

logger = logging.getLogger(__name__)


def index_pending_pdfs(db_path: Optional[str] = None) -> int:
    """Index les PDFs qui n'ont pas encore de chunks en base.

    Returns:
        Nombre de PDFs indexés.
    """
    path = db_path or config.DB_PATH
    docs_db = crud.list_documents(path)
    docs_indexed = {d["filename"] for d in docs_db if d.get("num_chunks", 0) > 0}
    pdf_files = list(config.PDF_DIR.glob("*.pdf"))
    pending = [f for f in pdf_files if f.name not in docs_indexed]

    if not pending:
        return 0

    all_splits = []
    for pdf_file in pending:
        try:
            docs = ingestion.load_pdf(str(pdf_file))
            splits = ingestion.chunk_documents(docs)
            all_splits.extend(splits)

            crud.create_document(
                filename=pdf_file.name,
                num_pages=len(docs),
                num_chunks=len(splits),
                db_path=path,
            )
            logger.info(f"PDF indexé : {pdf_file.name} ({len(splits)} chunks)")
        except Exception as e:
            logger.error(f"Erreur indexation {pdf_file.name}: {e}")

    if all_splits:
        try:
            embeddings = ingestion.create_embeddings(
                model_name=config.OLLAMA_EMBEDDING_MODEL
            )
            retriever = retriever_mod.get_or_create_retriever(
                model_name=config.OLLAMA_EMBEDDING_MODEL,
                top_k=config.TOP_K,
                persist_dir=str(config.CHROMA_DIR),
            )
            retriever_mod.add_documents_to_retriever(retriever, all_splits, embeddings)
            logger.info(f"{len(all_splits)} chunks ajoutés au retriever")
        except Exception as e:
            logger.error(f"Erreur embeddings: {e}")

    return len(pending)


def get_retriever():
    """Retourne le retriever ChromaDB."""
    return retriever_mod.get_or_create_retriever(
        model_name=config.OLLAMA_EMBEDDING_MODEL,
        top_k=config.TOP_K,
        persist_dir=str(config.CHROMA_DIR),
    )


def get_indexing_status(db_path: Optional[str] = None) -> dict:
    """Retourne le statut d'indexation des documents."""
    path = db_path or config.DB_PATH
    docs_db = crud.list_documents(path)
    pdf_files = list(config.PDF_DIR.glob("*.pdf"))
    indexed = sum(1 for d in docs_db if d.get("num_chunks", 0) > 0)

    return {
        "total_pdfs": len(pdf_files),
        "indexed": indexed,
        "pending": len(pdf_files) - indexed,
        "documents": [
            {"filename": d["filename"], "chunks": d.get("num_chunks", 0)}
            for d in docs_db
        ],
    }
