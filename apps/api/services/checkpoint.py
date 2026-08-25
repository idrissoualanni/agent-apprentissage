"""Service de checkpoint — gestion de l'état LangGraph persisté."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_thread_id_from_session(session_id: int, db_path: Optional[str] = None) -> Optional[str]:
    """Récupère le thread_id LangGraph associé à une session."""
    from apps.api.db import crud
    import apps.api.config as config

    path = db_path or config.DB_PATH

    with crud.get_connection(path) as conn:
        row = conn.execute(
            "SELECT langgraph_thread_id FROM session WHERE id = ?",
            (session_id,),
        ).fetchone()
        return row["langgraph_thread_id"] if row else None


def clear_checkpoint(thread_id: str) -> bool:
    """Supprime le checkpoint d'un thread (reset conversation).

    Returns:
        True si le checkpoint a été supprimé.
    """
    try:
        import sqlite3
        from apps.api.agent.graph import CHECKPOINT_DB

        conn = sqlite3.connect(str(CHECKPOINT_DB))
        conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        conn.commit()
        conn.close()
        logger.info(f"Checkpoint supprimé pour thread {thread_id[:8]}")
        return True
    except Exception as e:
        logger.error(f"Erreur clear checkpoint: {e}")
        return False
