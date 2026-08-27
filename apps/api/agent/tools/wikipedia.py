"""Outil de recherche Wikipédia — réponses factuelles précises.

Utilise les API officielles de Wikipédia (aucune dépendance externe ajoutée,
httpx est déjà utilisé par web_search) :
- API MediaWiki ``action=query&list=search``  → recherche de titres ;
- API REST ``/api/rest_v1/page/summary/{titre}`` → résumé structuré + URL.

L'agent s'en sert pour donner des réponses plus précises sur les définitions,
notions, personnes et faits établis — en complément du RAG documentaire et de
la recherche web (actualités/données récentes).
"""

import json
import logging
import re
from langchain.tools import tool

logger = logging.getLogger(__name__)

WIKI_TIMEOUT = 10.0
# Wikipédia exige un User-Agent descriptif avec une URL/email de contact
# (politique robots) ; sans contact valide l'API répond 403.
_USER_AGENT = "AgentApprentissageBot/3.0 (https://localhost; tuteur pedagogique)"


def _wiki_search_titles(query: str, lang: str, max_results: int) -> list:
    """Recherche Wikipédia (API MediaWiki) → titres + extraits."""
    import httpx
    r = httpx.get(
        f"https://{lang}.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": max_results,
            "format": "json",
            "utf8": 1,
        },
        timeout=WIKI_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    r.raise_for_status()
    data = r.json()
    return [
        {"title": item.get("title", ""), "snippet": item.get("snippet", "")}
        for item in data.get("query", {}).get("search", [])
    ]


def _wiki_summary(title: str, lang: str):
    """Résumé structuré d'un article (API REST Wikipédia), ou None."""
    import httpx
    from urllib.parse import quote
    r = httpx.get(
        f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}",
        timeout=WIKI_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    if r.status_code != 200:
        return None
    data = r.json()
    extract = (data.get("extract") or "").strip()
    if not extract:
        return None
    return {
        "title": data.get("title", title),
        "summary": extract,
        "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "description": data.get("description", "") or "",
    }


@tool
def wikipedia_search(query: str, lang: str = "fr", max_results: int = 3) -> str:
    """Recherche sur Wikipédia et retourne les résumés des articles pertinents.

    Args:
        query: Requête de recherche (notion, personne, événement, concept...)
        lang: Langue de Wikipédia ("fr" par défaut, "en" pour un sujet anglais)
        max_results: Nombre max d'articles retournés (défaut: 3)

    Returns:
        JSON string : liste de {title, summary, url, description}
        ou {"error": "..."} si le service est indisponible.
    """
    lang = (lang or "fr").strip().lower()[:2]
    try:
        hits = _wiki_search_titles(query, lang, max_results)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Wikipedia search failed: {e}")
        return json.dumps(
            {"error": f"Recherche Wikipédia indisponible : {e}"},
            ensure_ascii=False,
        )

    results = []
    for hit in hits:
        summary = None
        try:
            summary = _wiki_summary(hit["title"], lang)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Wikipedia summary failed for {hit['title']}: {e}")

        if summary:
            results.append(summary)
        else:
            # Repli : extrait de recherche, nettoyé des balises HTML <span>.
            snippet = re.sub(r"<[^>]+>", "", hit.get("snippet", "")).strip()
            results.append({
                "title": hit["title"],
                "summary": snippet,
                "url": f"https://{lang}.wikipedia.org/wiki/"
                       + hit["title"].replace(" ", "_"),
                "description": "",
            })
        if len(results) >= max_results:
            break

    return json.dumps(results, ensure_ascii=False)
