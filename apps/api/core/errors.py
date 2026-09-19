"""Gestion des erreurs API standardisées — Agent d'Apprentissage V4."""

from typing import Optional
from pydantic import BaseModel
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
import uuid

logger = logging.getLogger(__name__)


class APIError(BaseModel):
    """Schéma standardisé pour les erreurs API."""
    
    code: str  # Code d'erreur machine (ex: "RAG_001", "LLM_TIMEOUT")
    message: str  # Message lisible par l'utilisateur
    detail: Optional[str] = None  # Détails techniques pour le debug
    trace_id: str  # ID de trace pour le logging distribué


class AppException(Exception):
    """Exception métier personnalisée avec code d'erreur."""
    
    def __init__(
        self,
        code: str,
        message: str,
        detail: Optional[str] = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


# ═══════════════════════════════════════════════════════════════════════════
# Codes d'erreur par domaine
# ═══════════════════════════════════════════════════════════════════════════

class ErrorCode:
    """Taxonomie des codes d'erreur."""
    
    # LLM / Modèle
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    
    # RAG / Recherche
    RAG_NOT_FOUND = "RAG_NOT_FOUND"
    RAG_INDEX_ERROR = "RAG_INDEX_ERROR"
    RAG_RETRIEVAL_FAILED = "RAG_RETRIEVAL_FAILED"
    
    # Base de données
    DB_CONNECTION_ERROR = "DB_CONNECTION_ERROR"
    DB_LOCKED = "DB_LOCKED"
    DB_INTEGRITY_ERROR = "DB_INTEGRITY_ERROR"
    
    # Documents / Upload
    DOC_INVALID_TYPE = "DOC_INVALID_TYPE"
    DOC_TOO_LARGE = "DOC_TOO_LARGE"
    DOC_CORRUPTED = "DOC_CORRUPTED"
    DOC_UPLOAD_FAILED = "DOC_UPLOAD_FAILED"
    
    # Validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    VALIDATION_MISSING_FIELD = "VALIDATION_MISSING_FIELD"
    
    # Session / Utilisateur
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    
    # Autorisation
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_FORBIDDEN = "AUTH_FORBIDDEN"
    
    # Serveur
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# ═══════════════════════════════════════════════════════════════════════════
# Handlers globaux
# ═══════════════════════════════════════════════════════════════════════════

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handler pour les exceptions métier AppException."""
    
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4())[:8])
    
    logger.warning(
        f"[{trace_id}] Erreur métier: {exc.code} - {exc.message}",
        extra={"trace_id": trace_id, "code": exc.code}
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=APIError(
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            trace_id=trace_id,
        ).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handler pour les erreurs de validation Pydantic/FastAPI."""
    
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4())[:8])
    
    errors_detail = []
    for error in exc.errors():
        errors_detail.append({
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        })
    
    logger.warning(
        f"[{trace_id}] Erreur de validation: {errors_detail}",
        extra={"trace_id": trace_id}
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=APIError(
            code=ErrorCode.VALIDATION_ERROR,
            message="Données invalides",
            detail=str(errors_detail),
            trace_id=trace_id,
        ).model_dump(),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handler pour les HTTPException standards."""
    
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4())[:8])
    
    # Mapper les status codes vers des codes d'erreur
    code_map = {
        404: ErrorCode.SESSION_NOT_FOUND,
        422: ErrorCode.VALIDATION_ERROR,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }
    
    code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    
    logger.warning(
        f"[{trace_id}] HTTP {exc.status_code}: {exc.detail}",
        extra={"trace_id": trace_id}
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=APIError(
            code=code,
            message=str(exc.detail),
            trace_id=trace_id,
        ).model_dump(),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler global pour toutes les exceptions non gérées."""
    
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4())[:8])
    
    logger.error(
        f"[{trace_id}] Erreur interne: {str(exc)}",
        extra={"trace_id": trace_id},
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=APIError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Une erreur interne est survenue",
            detail="Veuillez réessayer ou contacter le support si le problème persiste",
            trace_id=trace_id,
        ).model_dump(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Exceptions utilitaires
# ═══════════════════════════════════════════════════════════════════════════

def raise_document_error(code: str, message: str, detail: Optional[str] = None):
    """Lève une exception pour une erreur document."""
    raise AppException(code=code, message=message, detail=detail, status_code=422)


def raise_llm_error(code: str, message: str, detail: Optional[str] = None):
    """Lève une exception pour une erreur LLM."""
    status_code = 503 if code == ErrorCode.LLM_UNAVAILABLE else 408
    raise AppException(code=code, message=message, detail=detail, status_code=status_code)


def raise_rag_error(code: str, message: str, detail: Optional[str] = None):
    """Lève une exception pour une erreur RAG."""
    raise AppException(code=code, message=message, detail=detail, status_code=400)


def raise_db_error(code: str, message: str, detail: Optional[str] = None):
    """Lève une exception pour une erreur base de données."""
    status_code = 503 if code == ErrorCode.DB_CONNECTION_ERROR else 400
    raise AppException(code=code, message=message, detail=detail, status_code=status_code)
