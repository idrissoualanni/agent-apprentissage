"""Service de streaming SSE — Server-Sent Events pour réponses token par token."""

import json
import logging
from typing import Generator

logger = logging.getLogger(__name__)


def format_sse_event(data: dict, event: str = "message") -> str:
    """Formate un dict en SSE event.

    Format:
        event: <event>\n
        data: <json>\n\n
    """
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {json_data}\n\n"


def stream_tokens(token_generator: Generator) -> Generator[str, None, None]:
    """Convertit un générateur de tokens en SSE stream.

    Args:
        token_generator: Générateur yieldant des dict {token, done, ...}

    Yields:
        Strings SSE formatées
    """
    for chunk in token_generator:
        if "error" in chunk:
            yield format_sse_event({"error": chunk["error"]}, event="error")
            yield format_sse_event({"done": True}, event="done")
            break

        if chunk.get("done"):
            metadata = chunk.get("metadata", {})
            yield format_sse_event({"done": True, **metadata}, event="done")
            break

        if chunk.get("token"):
            yield format_sse_event({"token": chunk["token"]}, event="token")


def stream_json_response(data: dict) -> str:
    """Formate une réponse JSON complète (non streaming)."""
    return json.dumps(data, ensure_ascii=False)
