"""Store d'artefacts — persistance en base via CRUD."""

import json
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def save_artifact(artifact_type: str, title: str, content: str,
                  session_id: int = 0) -> str:
    """Sauvegarde un artefact en base de données.

    Args:
        artifact_type: Type d'artefact (schema, quiz, code, chart)
        title: Titre de l'artefact
        content: Contenu JSON de l'artefact (string)
        session_id: ID de la session (optionnel)

    Returns:
        JSON string avec l'ID de l'artefact créé
    """
    from apps.api.db import crud

    try:
        artifact_id = crud.create_artifact(
            user_id="default_user",
            session_id=session_id if session_id else None,
            type=artifact_type,
            title=title,
            content=content,
            format="json",
        )
        return json.dumps({
            "artifact_id": artifact_id,
            "status": "saved",
            "type": artifact_type,
            "title": title,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save artifact: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
def list_user_artifacts(session_id: int = 0) -> str:
    """Liste les artefacts de l'utilisateur.

    Args:
        session_id: ID de la session pour filtrer (optionnel)

    Returns:
        JSON string avec la liste des artefacts
    """
    from apps.api.db import crud

    try:
        artifacts = crud.list_artifacts(
            user_id="default_user",
            session_id=session_id if session_id else None,
        )
        return json.dumps({
            "count": len(artifacts),
            "artifacts": [
                {
                    "id": a["id"],
                    "type": a["type"],
                    "title": a["title"],
                    "created_at": a["created_at"],
                }
                for a in artifacts
            ],
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to list artifacts: {e}")
        return json.dumps({"count": 0, "artifacts": [], "error": str(e)})
