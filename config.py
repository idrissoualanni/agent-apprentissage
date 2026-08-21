import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent

# ─── LLM ──────────────────────────────────────────────────────────────────
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")

# Nombre de couches GPU à utiliser (0 = CPU only, -1 = auto)
# Utile quand le GPU Vulkan n'a pas assez de VRAM (OOM)
OLLAMA_NUM_GPU = int(os.getenv("OLLAMA_NUM_GPU", "0"))

# ─── Ollama distant ────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")  # vide = localhost:11434
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")     # vide = pas d'auth

# ─── Modeles disponibles (separes par virgule) ────────────────────────────
_available_raw = os.getenv(
    "AVAILABLE_MODELS",
    "qwen2.5:1.5b,qwen2.5-coder:3b",
)
AVAILABLE_MODELS = [m.strip() for m in _available_raw.split(",") if m.strip()]

# ─── RAG ──────────────────────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
TOP_K = int(os.getenv("TOP_K", "3"))

# ─── Paths ────────────────────────────────────────────────────────────────
PDF_DIR = PROJECT_ROOT / "data" / "documents"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
DB_PATH = PROJECT_ROOT / "db" / "agent.db"
CHECKPOINT_DB = PROJECT_ROOT / "checkpoints.db"

# ─── Assure que les dossiers existent ─────────────────────────────────────
PDF_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
