"""Module LLM — factory Ollama (local ou distant)."""

from llm.cloud_providers import get_llm, list_local_models

__all__ = ["get_llm", "list_local_models"]
