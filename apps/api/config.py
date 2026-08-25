"""Config centralisee V3.

Reprend la logique V2 (lit .env a la racine du projet) pour eviter la duplication.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Charge le .env a la racine du projet (meme fichier que V2)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

PROJECT_ROOT = _PROJECT_ROOT

# ─── LLM ──────────────────────────────────────────────────────────────────
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")

OLLAMA_NUM_GPU = int(os.getenv("OLLAMA_NUM_GPU", "0"))

# ─── Ollama distant (cloud ou autre) ────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

# ─── Modeles disponibles ────────────────────────────────────────────────────
_available_raw = os.getenv(
    "AVAILABLE_MODELS",
    "qwen2.5:1.5b,qwen2.5-coder:3b",
)
AVAILABLE_MODELS = [m.strip() for m in _available_raw.split(",") if m.strip()]

# ─── RAG ──────────────────────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
TOP_K = int(os.getenv("TOP_K", "3"))

# RAG semantique : seuil de pertinence + confiance min pour utiliser le contexte
RAG_SEMANTIC_THRESHOLD = float(os.getenv("RAG_SEMANTIC_THRESHOLD", "0.3"))
RAG_MIN_CONFIDENCE = float(os.getenv("RAG_MIN_CONFIDENCE", "0.6"))
RAG_DOUBLE_CHECK_ENABLED = os.getenv("RAG_DOUBLE_CHECK_ENABLED", "true").lower() == "true"

# ─── Paths ────────────────────────────────────────────────────────────────
# En V3, on garde la compat avec V2 (memes fichiers DB)
PDF_DIR = PROJECT_ROOT / "data" / "documents"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
DB_PATH = PROJECT_ROOT / "db" / "agent.db"
CHECKPOINT_DB = PROJECT_ROOT / "checkpoints.db"

# V3 : nouveaux repertoires
MODEL_CACHE_DIR = PROJECT_ROOT / "data" / "model_cache"

# Assure que les repertoires existent
PDF_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)

# ─── Web search providers ──────────────────────────────────────────────────
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
WEB_SEARCH_DEFAULT_PROVIDER = os.getenv("WEB_SEARCH_DEFAULT_PROVIDER", "ddgs")
WEB_SEARCH_CACHE_TTL_HOURS = int(os.getenv("WEB_SEARCH_CACHE_TTL_HOURS", "24"))