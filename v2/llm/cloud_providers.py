"""Factory LLM — Ollama local ou distant.

Convention :
  - "qwen2.5:1.5b"           → Ollama (local ou distant selon OLLAMA_BASE_URL)
  - "minimax-m3"             → modèle Ollama Cloud

Si le serveur Ollama est distant (OLLAMA_BASE_URL non vide), on utilise un
wrapper compatible LangChain qui passe par le client ``ollama`` officiel,
capable d'envoyer la clé d'API via le header ``Authorization: Bearer ...``.
"""

from typing import Optional, Any, List
from langchain_core.messages import AIMessage, BaseMessage


# ─── Wrapper LangChain-compatible pour Ollama distant ────────────────────

class CloudOllamaChat:
    """Wrapper minimal compatible avec l'API ``.invoke([messages])`` de LangChain.

    Utilise le client officiel ``ollama`` (qui supporte l'authentification)
    plutôt que ``ChatOllama`` de langchain_ollama (qui ne supporte plus
    les headers d'authentification dans les versions recentes).
    """

    def __init__(self, model: str, temperature: float = 0.3, host: str = "", api_key: str = ""):
        import ollama as ollama_lib
        import os as _os

        # On exporte la cle dans l'env systematiquement (defense en profondeur)
        if api_key:
            _os.environ["OLLAMA_API_KEY"] = api_key

        client_kwargs = {}
        if host:
            client_kwargs["host"] = host
        # Le client ollama supporte le header Authorization si passe en env
        self._client = ollama_lib.Client(**client_kwargs) if client_kwargs else ollama_lib
        self._model = model
        self._temperature = temperature

    def invoke(self, messages: Any, **kwargs) -> AIMessage:
        # Convertit les messages LangChain en format Ollama
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
            content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else str(m))
            ollama_msgs.append({"role": role, "content": content})

        try:
            response = self._client.chat(
                model=self._model,
                messages=ollama_msgs,
                options={"temperature": self._temperature},
            )
        except Exception as e:
            # Fallback : si le header Authorization n'est pas envoye, on
            # essaie via httpx directement avec headers explicites.
            import os as _os
            api_key = _os.environ.get("OLLAMA_API_KEY", "")
            if api_key and "401" in str(e):
                import httpx
                host = self._client._client.base_url if hasattr(self._client, "_client") else "https://ollama.com"
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

        # Reponse Ollama : {"message": {"role": "assistant", "content": "..."}}
        content = ""
        if isinstance(response, dict):
            msg = response.get("message") or {}
            content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
        else:
            content = str(response)

        return AIMessage(content=content)


# ─── Factory publique ─────────────────────────────────────────────────────

def get_llm(
    model_name: str,
    temperature: float = 0.3,
    num_gpu: Optional[int] = None,
    **kwargs,
):
    """Retourne un chat model Ollama (local ou distant via Ollama Cloud)."""
    import config

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
    """Liste les modèles disponibles sur le serveur Ollama (local ou cloud)."""
    try:
        import ollama as ollama_lib
        import config
        import os as _os

        if config.OLLAMA_API_KEY:
            _os.environ["OLLAMA_API_KEY"] = config.OLLAMA_API_KEY

        client_kwargs = {}
        if config.OLLAMA_BASE_URL:
            client_kwargs["host"] = config.OLLAMA_BASE_URL
        client = ollama_lib.Client(**client_kwargs) if client_kwargs else ollama_lib
        response = client.list()
        return [m["model"] for m in response.get("models", [])]
    except Exception:
        return []
