"""Routes documents — upload PDF et gestion de la bibliothèque."""

import shutil
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional

from apps.api.db import crud
from apps.api.services import rag_service
import apps.api.config as config

router = APIRouter(tags=["documents"])


@router.get("")
async def list_documents():
    """ Liste les documents indexés."""
    docs = crud.list_documents(db_path=config.DB_PATH)
    return {"documents": docs}


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload un PDF et l'indexe dans ChromaDB."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Seuls les fichiers PDF sont acceptés")

    # Sauvegarder le fichier
    pdf_path = config.PDF_DIR / file.filename
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Indexer immédiatement
    try:
        count = rag_service.index_pending_pdfs()
        return {
            "ok": True,
            "filename": file.filename,
            "indexed": count > 0,
        }
    except Exception as e:
        return {
            "ok": True,
            "filename": file.filename,
            "indexed": False,
            "error": str(e),
        }


@router.get("/status")
async def indexing_status():
    """Retourne le statut d'indexation."""
    return rag_service.get_indexing_status()


@router.delete("/{filename}")
async def delete_document(filename: str):
    """Supprime un document."""
    pdf_path = config.PDF_DIR / filename
    if pdf_path.exists():
        pdf_path.unlink()
    return {"ok": True}
