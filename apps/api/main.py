"""Entry point FastAPI — Agent d'Apprentissage V3."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from apps.api.db.migrations import run_migrations
from apps.api.services import rag_service
import apps.api.config as config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # ── Startup ──
    logger.info("Démarrage API V3...")
    run_migrations(config.DB_PATH)
    indexed = rag_service.index_pending_pdfs()
    if indexed:
        logger.info(f"{indexed} PDF(s) indexé(s) au démarrage")
    yield
    # ── Shutdown ──
    logger.info("Arrêt API V3")


app = FastAPI(
    title="Agent d'Apprentissage API",
    version="3.0.0",
    description="API REST pour le frontend Next.js - V3",
    lifespan=lifespan,
)

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
        "version": "3.0.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


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
