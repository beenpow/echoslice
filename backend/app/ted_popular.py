from __future__ import annotations
from typing import Any
import requests

TED_ZENITH_SEARCH_URL = "https://zenith-prod-alt.ted.com/api/search"

DEFAULT_HITS_PER_PAGE = 24

class TedSearchError(RuntimeError):
    pass

def fetch_popular_slugs(
    page: int,
    hits_per_page: int = DEFAULT_HITS_PER_PAGE,
    timeout_sec: int = 10,
) -> list[str]:
    """
    Fetch popular TED talk slugs using TED's zenith search API.

    Returns:
      list[str] of slugs (e.g., "dan_pink_the_puzzle_of_motivation")
    """
    if page < 0:
        raise ValueError("page must be >= 0")
    if hits_per_page <= 0 or hits_per_page > 100:
        raise ValueError("hits_per_page must be between 1 and 100")

    payload = [
        {
            "indexName": "popular",
            "params": {
                "attributeForDistinct": "objectID",
                "distinct": 1,
                "facets": ["subtitle_languages", "tags"],
                "highlightPostTag": "__ais-highlight__",
                "highlightPreTag": "__ais-highlight__",
                "hitsPerPage": hits_per_page,
                "maxValuesPerFacet": 500,
                "page": page,
                "query": "",
            },
        }
    ]

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Origin은 없어도 되는 경우가 많지만, 브라우저 동작과 유사하게 맞춰줌
        "Origin": "https://www.ted.com",
        "Referer": "https://www.ted.com/talks?sort=popular",
    }

    try:
        resp = requests.post(
            TED_ZENITH_SEARCH_URL,
            json=payload,
            headers=headers,
            timeout=timeout_sec,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TedSearchError(f"TED zenith search request failed: {e}") from e
    
    try:
        data: dic[str, Any] = resp.json()
    except ValueError as e:
        raise TedSearchError("TED zenith search returned non-JSON response") from e

    # response shape:
    # { "results": [ { "hits": [ { "slug": ... }, ... ], "nbHits": ..., ... } ] }
    results = data.get("results")
    if not isinstance(results, list) or not results:
        raise TedSearchError("Unexpected response: missing results[]")

    first = results[0]
    hits = first.get("hits")
    if not isinstance(hits, list):
        raise TedSearchError("Unexpected response: missing hits[]")

    slugs: list[str] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        slug = h.get("slug")
        if isinstance(slug, str) and slug:
            slugs.append(slug)

    return slugs