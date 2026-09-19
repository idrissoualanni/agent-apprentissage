"""Routes documents — upload PDF et gestion de la bibliothèque V4."""

import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional

from apps.api.db import crud
from apps.api.services import rag_service
from apps.api.core.errors import AppException, ErrorCode
import apps.api.config as config

router = APIRouter(tags=["documents"])

# Constantes de validation
ALLOWED_MAX_SIZE = 20 * 1024 * 1024  # 20 MB
PDF_MAGIC_BYTES = b"%PDF-"


def validate_pdf_magic_bytes(content: bytes) -> bool:
    """Vérifie les magic bytes d'un fichier PDF."""
    return content[:5] == PDF_MAGIC_BYTES


@router.get("")
def list_documents():
    """Liste les documents indexés."""
    docs = crud.list_documents(db_path=config.DB_PATH)
    return {"documents": docs}


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload un PDF et l'indexe dans ChromaDB.
    
    Validation:
    - Magic bytes %PDF-
    - Taille maximale 20MB
    - Nom de fichier généré par UUID (pas de path traversal)
    """
    # Vérifier le type de fichier
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise AppException(
            code=ErrorCode.DOC_INVALID_TYPE,
            message="Seuls les fichiers PDF sont acceptés",
            status_code=422,
        )
    
    # Lire le contenu pour vérification
    try:
        content = await file.read()
    except Exception as e:
        raise AppException(
            code=ErrorCode.DOC_UPLOAD_FAILED,
            message="Échec de la lecture du fichier",
            detail=str(e),
            status_code=500,
        )
    
    # Vérifier la taille
    if len(content) > ALLOWED_MAX_SIZE:
        raise AppException(
            code=ErrorCode.DOC_TOO_LARGE,
            message=f"Fichier trop volumineux (max {ALLOWED_MAX_SIZE // (1024*1024)}MB)",
            detail=f"Taille: {len(content)} bytes",
            status_code=422,
        )
    
    # Vérifier les magic bytes PDF
    if not validate_pdf_magic_bytes(content):
        raise AppException(
            code=ErrorCode.DOC_CORRUPTED,
            message="Fichier PDF invalide ou corrompu",
            detail="Magic bytes incorrects",
            status_code=422,
        )
    
    # Générer un nom de fichier unique (UUID) pour éviter path traversal
    original_filename = Path(file.filename).name
    safe_filename = f"{uuid.uuid4()}.pdf"
    pdf_path = config.PDF_DIR / safe_filename
    
    # Sauvegarder le fichier
    try:
        with open(pdf_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise AppException(
            code=ErrorCode.DOC_UPLOAD_FAILED,
            message="Échec de la sauvegarde du fichier",
            detail=str(e),
            status_code=500,
        )
    
    # Indexer immédiatement
    try:
        count = rag_service.index_pending_pdfs()
        return {
            "ok": True,
            "filename": original_filename,
            "safe_filename": safe_filename,
            "indexed": count > 0,
            "chunks_added": count,
        }
    except Exception as e:
        # rollback: supprimer le fichier si l'indexation échoue
        if pdf_path.exists():
            pdf_path.unlink()
        raise AppException(
            code=ErrorCode.RAG_INDEX_ERROR,
            message="Échec de l'indexation du document",
            detail=str(e),
            status_code=500,
        )


@router.get("/status")
def indexing_status():
    """Retourne le statut d'indexation."""
    return rag_service.get_indexing_status()


@router.get("/artifacts")
def list_artifacts(session_id: Optional[int] = None, user_id: str = "default_user"):
    """Liste les artefacts d'apprentissage (quiz, schémas…) produits par l'agent.

    Correspond à l'appel frontend ``artifacts.list()`` (lib/api.ts), qui attend
    un tableau JSON brut.
    """
    return crud.list_artifacts(user_id=user_id, session_id=session_id, db_path=config.DB_PATH)


@router.delete("/{filename}")
def delete_document(filename: str):
    """Supprime un document."""
    # Sécurité: s'assurer que le filename ne contient pas de path traversal
    safe_filename = Path(filename).name
    
    pdf_path = config.PDF_DIR / safe_filename
    if pdf_path.exists():
        pdf_path.unlink()
    
    # TODO: Supprimer aussi les embeddings ChromaDB (BE-19)
    # rag_service.remove_document_from_chroma(safe_filename)
    
    return {"ok": True, "filename": safe_filename}
