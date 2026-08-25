"""Outil de recherche web multi-fournisseur — port V2 → V3."""

import json
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def web_search(query: str, provider: str = "ddgs", max_results: int = 5) -> str:
    """Recherche sur le web via différents fournisseurs.

    Args:
        query: Requête de recherche
        provider: Fournisseur à utiliser : "ddgs" (DuckDuckGo), "tavily", "brave"
        max_results: Nombre max de résultats (défaut: 5)

    Returns:
        JSON string avec liste de résultats (title, url, snippet)
    """
    from apps.api import config

    # Vérifier le cache
    try:
        from apps.api.db.crud import get_web_search_cache
        cached = get_web_search_cache(query, provider)
        if cached:
            return json.dumps(cached[:max_results], ensure_ascii=False)
    except Exception as e:
        logger.debug(f"Cache check failed: {e}")

    results = []

    if provider == "ddgs":
        results = _search_ddgs(query, max_results)
    elif provider == "tavily":
        results = _search_tavily(query, max_results)
    elif provider == "brave":
        results = _search_brave(query, max_results)
    else:
        logger.warning(f"Unknown provider: {provider}, falling back to ddgs")
        results = _search_ddgs(query, max_results)

    # Mettre en cache
    if results:
        try:
            from apps.api.db.crud import set_web_search_cache
            set_web_search_cache(query, provider, results)
        except Exception as e:
            logger.debug(f"Cache set failed: {e}")

    return json.dumps(results[:max_results], ensure_ascii=False)


def _search_ddgs(query: str, max_results: int) -> list[dict]:
    """Recherche DuckDuckGo."""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                })
        return results
    except Exception as e:
        logger.error(f"DDGS search failed: {e}")
        return []


def _search_tavily(query: str, max_results: int) -> list[dict]:
    """Recherche Tavily."""
    from apps.api import config
    api_key = config.TAVILY_API_KEY
    if not api_key:
        logger.warning("Tavily API key not configured")
        return _search_ddgs(query, max_results)

    try:
        import httpx
        r = httpx.post(
            "https://api.tavily.com/search",
            json={
                "query": query,
                "max_results": max_results,
                "api_key": api_key,
            },
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            }
            for item in data.get("results", [])
        ]
    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return []


def _search_brave(query: str, max_results: int) -> list[dict]:
    """Recherche Brave Search."""
    from apps.api import config
    api_key = config.BRAVE_API_KEY
    if not api_key:
        logger.warning("Brave API key not configured")
        return _search_ddgs(query, max_results)

    try:
        import httpx
        r = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"X-Subscription-Token": api_key},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            }
            for item in data.get("web", {}).get("results", [])
        ]
    except Exception as e:
        logger.error(f"Brave search failed: {e}")
        return []
