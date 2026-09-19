"""Entry point FastAPI — Agent d'Apprentissage V4."""

import logging
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from apps.api.db.migrations import run_migrations
from apps.api.services import rag_service
from apps.api.core.errors import (
    app_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    general_exception_handler,
    AppException,
    ErrorCode,
)
from apps.api.db.database import get_db_engine
import apps.api.config as config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_ollama_health() -> bool:
    """Vérifie la connexion à Ollama avec timeout court."""
    try:
        base_url = config.OLLAMA_BASE_URL.rstrip("/")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # ── Startup ──
    logger.info("Démarrage API V4...")
    
    # Initialiser la base de données avec WAL mode
    engine = get_db_engine(config.DB_PATH)
    with engine.connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
    
    run_migrations(config.DB_PATH)
    
    # Vérifier Ollama au démarrage (warning seulement, pas bloquant)
    ollama_ok = await check_ollama_health()
    if not ollama_ok:
        logger.warning(f"Ollama non disponible à {config.OLLAMA_BASE_URL}")
    else:
        logger.info("Ollama connecté avec succès")
    
    indexed = rag_service.index_pending_pdfs()
    if indexed:
        logger.info(f"{indexed} PDF(s) indexé(s) au démarrage")
    
    yield
    
    # ── Shutdown ──
    logger.info("Arrêt API V4")


app = FastAPI(
    title="Agent d'Apprentissage API",
    version="4.0.0",
    description="API REST pour le frontend Next.js - V4",
    lifespan=lifespan,
)

# Enregistrement des handlers d'erreurs
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# CORS pour le dev Next.js et le frontend Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://web-seven-nu-xdmbicvsxb.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "Agent d'Apprentissage",
        "version": "4.0.0",
        "status": "running",
    }


@app.get("/health/live")
def health_live():
    """Liveness probe - le process répond."""
    return {"status": "ok", "type": "live"}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe - DB + ChromaDB + Ollama OK."""
    checks = {"database": False, "chromadb": False, "ollama": False}
    
    # Vérifier base de données
    try:
        from apps.api.db.crud import get_db_connection
        conn = get_db_connection(config.DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
        checks["database"] = True
    except Exception as e:
        logger.warning(f"DB check failed: {e}")
    
    # Vérifier ChromaDB
    try:
        from apps.api.rag.retriever import get_or_create_retriever
        retriever = get_or_create_retriever()
        count = retriever.count()
        checks["chromadb"] = True
    except Exception as e:
        logger.warning(f"ChromaDB check failed: {e}")
    
    # Vérifier Ollama
    checks["ollama"] = await check_ollama_health()
    
    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503
    
    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }, status_code


# ── Routes ────────────────────────────────────────────────────────────────
from apps.api.routes.chat import router as chat_router
from apps.api.routes.sessions import router as sessions_router
from apps.api.routes.documents import router as documents_router
from apps.api.routes.profile import router as profile_router
from apps.api.routes.progress import router as progress_router
from apps.api.routes.models import router as models_router
from apps.api.ws.router import router as ws_router

app.include_router(chat_router, prefix="/api/chat")
app.include_router(sessions_router, prefix="/api/sessions")
app.include_router(documents_router, prefix="/api/documents")
app.include_router(profile_router, prefix="/api/profile")
app.include_router(progress_router, prefix="/api/progress")
app.include_router(models_router, prefix="/api/models")
app.include_router(ws_router)  # WebSocket : /ws/{session_id} (pas de prefix)
