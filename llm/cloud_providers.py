"""Factory LLM — Ollama local ou distant.

Convention :
  - "qwen2.5:1.5b"           → Ollama (local ou distant selon OLLAMA_BASE_URL)
  - "ollama/deepseek-r1:8b"  → idem, préfixe explicite ignoré
"""

from typing import Optional


def get_llm(
    model_name: str,
    temperature: float = 0.3,
    num_gpu: Optional[int] = None,
    **kwargs,
):
    """Retourne un ChatOllama configuré (local ou distant).

    Args:
        model_name: Nom du modèle Ollama
        temperature: Température de sampling
        num_gpu: Couches GPU (None = auto depuis config)
        **kwargs: Arguments additionnels passés au constructeur
    """
    from langchain_ollama import ChatOllama
    import config

    if num_gpu is None:
        num_gpu = config.OLLAMA_NUM_GPU

    ollama_kwargs = {
        "model": model_name,
        "temperature": temperature,
        "num_gpu": num_gpu,
    }

    # Serveur distant
    if config.OLLAMA_BASE_URL:
        ollama_kwargs["base_url"] = config.OLLAMA_BASE_URL

    # Auth si configurée
    if config.OLLAMA_API_KEY:
        ollama_kwargs["headers"] = {
            "Authorization": f"Bearer {config.OLLAMA_API_KEY}",
        }

    ollama_kwargs.update(kwargs)
    return ChatOllama(**ollama_kwargs)


def list_local_models() -> list[str]:
    """Liste les modèles disponibles sur le serveur Ollama."""
    try:
        import ollama as ollama_lib
        # Si serveur distant, pointer dessus
        import config
        client_kwargs = {}
        if config.OLLAMA_BASE_URL:
            client_kwargs["host"] = config.OLLAMA_BASE_URL
        if config.OLLAMA_API_KEY:
            client_kwargs["headers"] = {
                "Authorization": f"Bearer {config.OLLAMA_API_KEY}",
            }
        client = ollama_lib.Client(**client_kwargs) if client_kwargs else ollama_lib
        response = client.list() if client_kwargs else ollama_lib.list()
        return [m["model"] for m in response.get("models", [])]
    except Exception:
        return []
