"""Constructeurs de messages du protocole WebSocket.

Spec : docs/superpowers/specs/2026-08-27-websocket-cache-design.md (§3.2)
"""


def token_msg(text: str) -> dict:
    return {"type": "token", "text": text}


def final_message_msg(result: dict) -> dict:
    return {
        "type": "message",
        "answer": result.get("answer", ""),
        "method": result.get("method"),
        "thread_id": result.get("thread_id"),
        "artifacts": result.get("artifacts", []),
        "tool_transparency": result.get("tool_transparency", []),
    }


def confirmation_request_msg(confirmation_type, prompt) -> dict:
    return {
        "type": "confirmation_request",
        "confirmation_type": confirmation_type,
        "confirmation_prompt": prompt,
    }


def notification_msg(kind: str, data: dict) -> dict:
    return {"type": "notification", "kind": kind, "data": data}


def error_msg(message: str) -> dict:
    return {"type": "error", "message": message}


def pong_msg() -> dict:
    return {"type": "pong"}
