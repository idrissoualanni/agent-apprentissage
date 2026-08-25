"""Model Manager V3 — catalogue unifie, format control, fallback automatique.

Concepts cles :
- Chaque operation (chat, quiz, artifact, etc.) a un modele par defaut
- Chaque modele a un format_mode (strict_json / json_or_markdown / markdown / free_text)
- Le parser de sortie est adapte au format_mode
- Fallback automatique en cas d'echec (401, timeout)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import apps.api.config as config

logger = logging.getLogger(__name__)


# ─── Catalogue par defaut ──────────────────────────────────────────────────

DEFAULT_CATALOG: list[dict] = [
    # ── Locaux ──
    {
        "model_name": "qwen2.5:1.5b",
        "display_name": "Qwen 2.5 1.5B (Local)",
        "provider": "ollama_local",
        "default_temperature": 0.2,
        "format_mode": "strict_json",
        "max_tokens": 2048,
    },
    {
        "model_name": "qwen2.5-coder:3b",
        "display_name": "Qwen 2.5 Coder 3B (Local)",
        "provider": "ollama_local",
        "default_temperature": 0.2,
        "format_mode": "strict_json",
        "max_tokens": 2048,
    },
    {
        "model_name": "qwen3-embedding:0.6b",
        "display_name": "Qwen3 Embedding 0.6B (Local)",
        "provider": "ollama_local",
        "default_temperature": 0.0,
        "format_mode": "free_text",
        "max_tokens": 512,
    },
    # ── Ollama Cloud ──
    {
        "model_name": "minimax-m3",
        "display_name": "minimax-m3 (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.3,
        "format_mode": "json_or_markdown",
        "max_tokens": 4096,
    },
    {
        "model_name": "qwen3.5:397b",
        "display_name": "Qwen 3.5 397B (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.3,
        "format_mode": "json_or_markdown",
        "max_tokens": 8192,
    },
    {
        "model_name": "kimi-k2.7-code",
        "display_name": "Kimi K2.7 Code (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.2,
        "format_mode": "strict_json",
        "max_tokens": 4096,
    },
    {
        "model_name": "deepseek-v4-flash:preview",
        "display_name": "DeepSeek V4 Flash (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.3,
        "format_mode": "json_or_markdown",
        "max_tokens": 4096,
    },
    {
        "model_name": "gpt-oss:120b",
        "display_name": "GPT-OSS 120B (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.3,
        "format_mode": "json_or_markdown",
        "max_tokens": 4096,
    },
]


# ─── Presets par type d'operation ──────────────────────────────────────────

OPERATION_PRESETS: dict[str, dict] = {
    "chat":              {"model_name": "minimax-m3",            "temperature": 0.3},
    "quiz_generation":   {"model_name": "qwen2.5-coder:3b",      "temperature": 0.2},
    "feynman_eval":      {"model_name": "minimax-m3",            "temperature": 0.2},
    "artifact":          {"model_name": "kimi-k2.7-code",        "temperature": 0.5},
    "diagnostic":        {"model_name": "minimax-m3",            "temperature": 0.3},
    "relevance_check":   {"model_name": "qwen2.5-coder:3b",      "temperature": 0.0},
    "summarize":         {"model_name": "minimax-m3",            "temperature": 0.3},
}


# ─── Parsers de sortie adaptes au format_mode ──────────────────────────────

class StrictJSONParser:
    """Le modele DOIT renvoyer du JSON valide. Sinon erreur."""

    def parse(self, content: str) -> dict:
        content = content.strip()
        # Cherche un bloc ```json ... ```
        if "```json" in content:
            start = content.index("```json") + len("```json")
            end = content.index("```", start)
            content = content[start:end].strip()
        elif content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        try:
            data = json.loads(content)
            return {"type": "json", "data": data}
        except json.JSONDecodeError as e:
            raise ValueError(f"Expected JSON, got: {content[:100]}... ({e})")


class HybridParser:
    """Essaie JSON strict, puis fallback sur Markdown brut."""

    def parse(self, content: str) -> dict:
        # Tente d'abord le parsing JSON strict
        try:
            data = StrictJSONParser().parse(content)
            return data
        except ValueError:
            pass
        # Fallback : markdown brut
        return {"type": "markdown", "data": content}


class MarkdownParser:
    """Accepte tout en Markdown. Pas de parsing structure."""

    def parse(self, content: str) -> dict:
        return {"type": "markdown", "data": content}


class FreeTextParser:
    """Pas de format attendu. Tout passe en texte libre."""

    def parse(self, content: str) -> dict:
        return {"type": "text", "data": content}


PARSERS = {
    "strict_json":       StrictJSONParser,
    "json_or_markdown":  HybridParser,
    "markdown":          MarkdownParser,
    "free_text":         FreeTextParser,
}


# ─── Wrappers LLM avec format control ──────────────────────────────────────

class FormatControlledLLM:
    """Wrap un LLM (CloudOllamaChat ou ChatOllama) et parse la sortie selon format_mode."""

    def __init__(self, llm: Any, model_name: str, format_mode: str):
        self.llm = llm
        self.model_name = model_name
        self.format_mode = format_mode
        self.parser = PARSERS.get(format_mode, FreeTextParser)()

    def invoke(self, messages: Any) -> "ParsedResponse":
        """Appelle le LLM et parse la sortie."""
        response = self.llm.invoke(messages)
        raw = getattr(response, "content", str(response))
        parsed = self.parser.parse(raw)
        return ParsedResponse(
            raw=raw,
            parsed=parsed,
            model_name=self.model_name,
            format_mode=self.format_mode,
        )


class ParsedResponse:
    """Réponse LLM avec version brute et version parsée."""

    def __init__(self, raw: str, parsed: dict, model_name: str, format_mode: str):
        self.raw = raw
        self.parsed = parsed
        self.model_name = model_name
        self.format_mode = format_mode

    @property
    def content(self) -> str:
        """Contenu textuel (compat avec LangChain AIMessage)."""
        if self.parsed["type"] == "json":
            return json.dumps(self.parsed["data"], ensure_ascii=False)
        return self.parsed["data"]

    def __repr__(self):
        return f"ParsedResponse(model={self.model_name}, type={self.parsed['type']})"


# ─── Model Manager singleton ────────────────────────────────────────────────

class ModelManager:
    def __init__(self):
        self._catalog = {m["model_name"]: m for m in DEFAULT_CATALOG}
        self._fallback_chain: list[str] = [
            "minimax-m3", "qwen3.5:397b", "kimi-k2.7-code", "qwen2.5:1.5b",
        ]

    def get_llm(self, operation: str, **overrides) -> FormatControlledLLM:
        """Retourne un LLM configure pour l'operation demandee."""
        preset = {**OPERATION_PRESETS.get(operation, OPERATION_PRESETS["chat"]), **overrides}
        model_name = preset["model_name"]
        temperature = preset.get("temperature", 0.3)

        model_config = self._catalog.get(model_name)
        if not model_config:
            # Modele inconnu : on prend le chat par defaut
            model_config = self._catalog[OPERATION_PRESETS["chat"]["model_name"]]
            model_name = model_config["model_name"]
            logger.warning(f"Unknown model '{model_name}', fallback to {model_name}")

        format_mode = model_config.get("format_mode", "json_or_markdown")
        provider = model_config["provider"]

        # Instanciation
        if provider == "ollama_cloud":
            llm = self._make_cloud_llm(model_name, temperature)
        else:
            llm = self._make_local_llm(model_name, temperature)

        return FormatControlledLLM(llm, model_name, format_mode)

    def _make_cloud_llm(self, model_name: str, temperature: float):
        """Crée un LLM Cloud Ollama via le wrapper."""
        # Importe ici pour eviter circular imports
        from apps.api.llm.cloud_providers import CloudOllamaChat
        return CloudOllamaChat(
            model=model_name,
            temperature=temperature,
            host=config.OLLAMA_BASE_URL,
            api_key=config.OLLAMA_API_KEY or "",
        )

    def _make_local_llm(self, model_name: str, temperature: float):
        """Crée un LLM Ollama local."""
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            num_gpu=config.OLLAMA_NUM_GPU,
        )

    def list_available(self) -> list[dict]:
        """Retourne le catalogue complet (lecture seule)."""
        return list(self._catalog.values())

    def get_config(self, model_name: str) -> Optional[dict]:
        return self._catalog.get(model_name)

    def fallback(self, failed_model: str) -> str:
        """Retourne le modele suivant dans la chaine de fallback."""
        try:
            idx = self._fallback_chain.index(failed_model)
            if idx + 1 < len(self._fallback_chain):
                return self._fallback_chain[idx + 1]
        except ValueError:
            pass
        return self._fallback_chain[0]

    def refresh_from_ollama(self) -> dict:
        """Rafraichit le catalogue depuis Ollama local + cloud."""
        try:
            import ollama
            client_kwargs = {}
            if config.OLLAMA_BASE_URL:
                client_kwargs["host"] = config.OLLAMA_BASE_URL
            client = ollama.Client(**client_kwargs) if client_kwargs else ollama

            models = client.list()
            remote_names = [m["model"] for m in models.get("models", [])]

            added = 0
            for name in remote_names:
                if name not in self._catalog:
                    self._catalog[name] = {
                        "model_name": name,
                        "display_name": f"{name} (Auto)",
                        "provider": "ollama_cloud" if config.OLLAMA_BASE_URL else "ollama_local",
                        "default_temperature": 0.3,
                        "format_mode": "json_or_markdown",
                        "max_tokens": 2048,
                    }
                    added += 1
            return {"added": added, "total": len(self._catalog)}
        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            return {"added": 0, "total": len(self._catalog), "error": str(e)}


# Singleton global
MODEL_MANAGER = ModelManager()