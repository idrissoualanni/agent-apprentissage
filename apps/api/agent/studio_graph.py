"""Point d'entrée pour LangGraph Studio — expose le graph compilé au niveau module.

Ce fichier initialise les dépendances et expose `graph` (le StateGraph compilé)
afin que LangGraph Studio puisse le trouver via langgraph.json.

Points clés pour le debugging :
  - ModelManager en mode `force_local=False` : les LLMs cloud (minimax-m3,
    kimi-k2.7-code…) sont utilisés selon OPERATION_PRESETS. ⚠️ Consomme du
    quota Ollama Cloud. Les embeddings restent locaux.
  - Retriever ChromaDB réel, avec fallback sur un mock vide si indisponible.
  - `with_checkpointer=False` : Studio gère son propre checkpointing pour
    permettre le time-travel debugging (rejouer chaque nœud).

Usage:
    langgraph dev    # depuis la racine du projet (lit langgraph.json)

Prérequis:
    - Ollama local lancé (pour les embeddings qwen3-embedding:0.6b)
    - Variable OLLAMA_API_KEY définie dans .env.studio (pour le cloud)
    - pip install "langgraph-cli[inmem]"
"""

import sys
import logging
from pathlib import Path

# ── Assure que apps.api est importable ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("studio_graph")

from apps.api.agent.graph import build_agent_graph
from apps.api.rag import retriever as retriever_mod
from apps.api.services.model_manager import ModelManager
import apps.api.config as config


def _build_retriever():
    """Crée le retriever ChromaDB, avec fallback sur un mock vide."""
    try:
        return retriever_mod.get_or_create_retriever(
            model_name=config.OLLAMA_EMBEDDING_MODEL,
            top_k=config.TOP_K,
            persist_dir=str(config.CHROMA_DIR),
        )
    except Exception as e:
        logger.warning(f"Retriever ChromaDB indisponible ({e}); mock vide utilisé.")

        class _MockRetriever:
            def invoke(self, query):
                return []

        return _MockRetriever()


# ── Initialisation des dépendances ──
# 1. ModelManager en mode CLOUD (utilise minimax-m3, kimi-k2.7-code… selon les presets)
#    ⚠️ Consomme du quota Ollama Cloud. Mettre force_local=True pour revenir au local.
model_manager = ModelManager(force_local=False)

# 2. Retriever ChromaDB (embeddings locaux)
retriever = _build_retriever()

# ── Graph compilé au niveau module ──
# C'est cette variable que langgraph.json référence.
# with_checkpointer=False : Studio gère son propre checkpointing.
graph = build_agent_graph(
    retriever=retriever,
    model_manager=model_manager,
    db_path=str(config.DB_PATH),
    with_checkpointer=False,
)

logger.info("Graphe Studio prêt. Nodes : %s", list(graph.get_graph().nodes.keys()))
