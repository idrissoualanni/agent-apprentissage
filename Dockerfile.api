# ─── Backend FastAPI — Agent d'Apprentissage ──────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Dependances systeme (sqlite, build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dependances Python
COPY apps/api/requirements.txt ./apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt

# Code applicatif
COPY apps/api ./apps/api
COPY apps/api/db/schema_v3.sql ./apps/api/db/schema_v3.sql

# Dossiers de donnees (DB SQLite + Chroma + documents)
RUN mkdir -p /app/db /app/data/chroma /app/data/documents

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/app/db/agent.db \
    CHECKPOINT_DB=/app/checkpoints.db \
    CHROMA_DIR=/app/data/chroma

EXPOSE 8000

# Demarrage : migrations + uvicorn
CMD ["python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
