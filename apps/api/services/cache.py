"""Caches memoire TTL+LRU (cachetools) avec invalidation explicite.

Bornes strictes pour la machine Fly 512 Mo : maxsize limites, LRU evince
automatiquement. Pas de cache des reponses LLM (volontaire, voir spec
docs/superpowers/specs/2026-08-27-websocket-cache-design.md).
"""
import hashlib
import threading

from cachetools import TTLCache

PROFILE_TTL = 30        # secondes
COMPETENCY_TTL = 30
RAG_TTL = 600           # 10 minutes

_lock = threading.Lock()
profile_cache: TTLCache = TTLCache(maxsize=64, ttl=PROFILE_TTL)
competency_cache: TTLCache = TTLCache(maxsize=64, ttl=COMPETENCY_TTL)
rag_cache: TTLCache = TTLCache(maxsize=128, ttl=RAG_TTL)


def cache_get(cache: TTLCache, key: str):
    with _lock:
        return cache.get(key)


def cache_set(cache: TTLCache, key: str, value) -> None:
    with _lock:
        cache[key] = value


def invalidate_profile(user_id: str) -> None:
    """Invalide toutes les entrees du profil (quel que soit le db_path)."""
    with _lock:
        prefix = f"{user_id}|"
        for key in [k for k in profile_cache
                    if k == user_id or k.startswith(prefix)]:
            profile_cache.pop(key, None)


def invalidate_competencies(domain: str = None) -> None:
    """Invalide les competences d'un domaine (ou tout si domain=None)."""
    with _lock:
        if domain is None:
            competency_cache.clear()
        else:
            prefix = f"{domain}|"
            for key in [k for k in competency_cache
                        if k == domain or k.startswith(prefix)]:
                competency_cache.pop(key, None)


def rag_key(question: str, top_k: int) -> str:
    raw = f"{question.strip().lower()}|{top_k}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def clear_all() -> None:
    with _lock:
        profile_cache.clear()
        competency_cache.clear()
        rag_cache.clear()
