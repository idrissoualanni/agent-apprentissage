"""Factory LLM — Ollama local ou distant.

Port de V2 llm/cloud_providers.py pour FastAPI V3.
Supporte sync + async, auth via headers, fallback automatique.
"""

from typing import Optional, Any, List
from langchain_core.messages import AIMessage, BaseMessage
import logging

logger = logging.getLogger(__name__)


# ─── Wrapper LangChain-compatible pour Ollama distant ────────────────────

class CloudOllamaChat:
    """Wrapper compatible LangChain pour Ollama distant (Ollama Cloud).

    Utilise le client officiel ``ollama`` avec authentification.
    Supporte invoke() sync et ainvoke() async.
    """

    def __init__(self, model: str, temperature: float = 0.3,
                 host: str = "", api_key: str = ""):
        import ollama as ollama_lib
        import os as _os

        if api_key:
            _os.environ["OLLAMA_API_KEY"] = api_key

        client_kwargs = {}
        if host:
            client_kwargs["host"] = host

        self._client = ollama_lib.Client(**client_kwargs) if client_kwargs else ollama_lib
        self._model = model
        self._temperature = temperature

    def _convert_messages(self, messages: Any) -> List[dict]:
        """Convertit les messages LangChain en format Ollama."""
        ollama_msgs: List[dict] = []
        for m in messages:
            role = "user"
            if hasattr(m, "type"):
                t = m.type
                if t == "human":
                    role = "user"
                elif t == "ai":
                    role = "assistant"
                elif t == "system":
                    role = "system"
            elif isinstance(m, dict):
                role = m.get("role", "user")
            content = (
                getattr(m, "content", None)
                or (m.get("content") if isinstance(m, dict) else str(m))
            )
            ollama_msgs.append({"role": role, "content": content})
        return ollama_msgs

    def invoke(self, messages: Any, **kwargs) -> AIMessage:
        """Appel synchrone au LLM."""
        ollama_msgs = self._convert_messages(messages)

        try:
            response = self._client.chat(
                model=self._model,
                messages=ollama_msgs,
                options={"temperature": self._temperature},
            )
        except Exception as e:
            import os as _os
            api_key = _os.environ.get("OLLAMA_API_KEY", "")
            if api_key and "401" in str(e):
                import httpx
                host = (
                    self._client._client.base_url
                    if hasattr(self._client, "_client")
                    else "https://ollama.com"
                )
                r = httpx.post(
                    f"{host}/api/chat",
                    json={
                        "model": self._model,
                        "messages": ollama_msgs,
                        "stream": False,
                        "options": {"temperature": self._temperature},
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=60.0,
                )
                r.raise_for_status()
                response = r.json()
            else:
                raise

        # Le client ollama Python renvoie un objet ChatResponse (pas un dict).
        # On extrait .message.content — getattr imbriqué = 1 seul check booléen.
        content = ""

        # 1) ChatResponse du client ollama : response.message.content
        msg_obj = getattr(response, "message", None)
        if msg_obj is not None:
            content = getattr(msg_obj, "content", "") or ""

        # 2) Dict brut (fallback httpx)
        if not content and isinstance(response, dict):
            msg = response.get("message") or {}
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")

        # 3) Dernier recours : regex sur repr() pour extraire content="..."
        if not content:
            import re
            raw = repr(response)
            m = re.search(r"content=['\"](.+?)['\"]", raw)
            content = m.group(1) if m else str(response)

        return AIMessage(content=str(content))

    async def ainvoke(self, messages: Any, **kwargs) -> AIMessage:
        """Appel asynchrone — fallback sur invoke pour ollama sync client."""
        return self.invoke(messages, **kwargs)


# ─── Factory publique ─────────────────────────────────────────────────────

def get_llm(
    model_name: str,
    temperature: float = 0.3,
    num_gpu: Optional[int] = None,
    **kwargs,
):
    """Retourne un chat model Ollama (local ou distant via Ollama Cloud)."""
    from apps.api import config

    if config.OLLAMA_BASE_URL:
        return CloudOllamaChat(
            model=model_name,
            temperature=temperature,
            host=config.OLLAMA_BASE_URL,
            api_key=config.OLLAMA_API_KEY or "",
        )

    from langchain_ollama import ChatOllama

    if num_gpu is None:
        num_gpu = config.OLLAMA_NUM_GPU

    ollama_kwargs = {
        "model": model_name,
        "temperature": temperature,
        "num_gpu": num_gpu,
    }
    ollama_kwargs.update(kwargs)
    return ChatOllama(**ollama_kwargs)


def list_local_models() -> list[str]:
    """Liste les modèles disponibles sur le serveur Ollama."""
    try:
        import ollama as ollama_lib
        from apps.api import config
        import os as _os

        if config.OLLAMA_API_KEY:
            _os.environ["OLLAMA_API_KEY"] = config.OLLAMA_API_KEY

        client_kwargs = {}
        if config.OLLAMA_BASE_URL:
            client_kwargs["host"] = config.OLLAMA_BASE_URL
        client = ollama_lib.Client(**client_kwargs) if client_kwargs else ollama_lib
        response = client.list()
        return [m["model"] for m in response.get("models", [])]
    except Exception as e:
        logger.warning(f"Failed to list Ollama models: {e}")
        return []
