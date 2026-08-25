"""Outil de recherche web pour enrichir les réponses."""

import json
from langchain.tools import tool
from ddgs import DDGS


@tool
def web_search(query: str, num_results: int = 3) -> str:
    """Recherche sur le web pour enrichir une réponse.

    Args:
        query: Requête de recherche
        num_results: Nombre de résultats (défaut: 3)

    Returns:
        JSON string avec les résultats (title, url, snippet)
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
            formatted = [
                {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
                for r in results
            ]
            return json.dumps(formatted, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})
