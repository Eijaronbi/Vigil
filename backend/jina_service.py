import logging

import httpx

from backend.config import settings

logger = logging.getLogger("vigil.search")

JINA_READER_URL = "https://r.jina.ai"
JINA_SEARCH_URL = "https://s.jina.ai"
JINA_DEEPSEARCH_URL = "https://deepsearch.jina.ai/v1/chat/completions"
SERPER_URL = "https://google.serper.dev/search"
TIMEOUT = 60


def _jina_headers() -> dict:
    headers = {"Accept": "application/json"}
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"
    return headers


# ── Hound (keyless, anti-bot fetch + multi-engine search) ──


async def _hound_fetch(url: str) -> str | None:
    try:
        from master_fetch.fetcher import http_get
        from master_fetch.extractor import extract_content

        resp = await http_get(url, timeout=TIMEOUT)
        if resp.status != 200:
            return None
        extracted = extract_content(resp, extraction_type="markdown")
        text = "\n".join(extracted).strip() if extracted else None
        return text[:10000] if text else None
    except Exception:
        return None


async def _hound_search(query: str) -> str | None:
    try:
        from master_fetch.search_engines import multi_search

        ranked, _ = await multi_search(query, max_results=5)
        if not ranked:
            return None
        parts = []
        for i, r in enumerate(ranked[:5], 1):
            parts.append(
                f"{i}. {r.title}\n   URL: {r.url}\n   {r.snippet[:400]}"
            )
        return "\n\n".join(parts)
    except Exception:
        return None


# ── Jina Reader (fetch any public URL as clean text, fallback) ──


async def _jina_reader(url: str) -> str | None:
    if not settings.jina_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{JINA_READER_URL}/{url}",
                headers=_jina_headers(),
                json={"url": url},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            content = data.get("data", {}).get("content", "")
            return content.strip() if content else None
    except Exception:
        return None


# ── Web Search (Hound → Jina DeepSearch → Jina Search → Serper → DuckDuckGo) ──


async def _jina_deepsearch(query: str) -> str | None:
    if not settings.jina_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                JINA_DEEPSEARCH_URL,
                headers=_jina_headers(),
                json={
                    "model": "jina-deepsearch-v1",
                    "messages": [{"role": "user", "content": query}],
                    "stream": False,
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception:
        return None


async def _format_results(results: list[dict]) -> str | None:
    if not results:
        return None
    parts = []
    for i, r in enumerate(results[:5], 1):
        parts.append(
            f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['content'][:400]}"
        )
    return "\n\n".join(parts)


async def _serper_search(query: str) -> str | None:
    if not settings.serper_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                SERPER_URL,
                headers={
                    "X-API-KEY": settings.serper_api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": 5},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = []
            for item in data.get("organic", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "content": item.get("snippet", ""),
                })
            return await _format_results(results)
    except Exception:
        return None


async def _ddg_search(query: str) -> str | None:
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", ""),
                })
        return await _format_results(results)
    except Exception:
        return None


async def _jina_search(query: str) -> str | None:
    if not settings.jina_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                JINA_SEARCH_URL,
                headers=_jina_headers(),
                json={"q": query},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = []
            for item in data.get("data", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                })
            return await _format_results(results)
    except Exception:
        return None


# ── Public API ──


async def fetch_url(url: str) -> str | None:
    result = await _hound_fetch(url)
    if result:
        logger.info("fetch_url provider=hound url=%r", url)
        return result
    result = await _jina_reader(url)
    if result:
        logger.info("fetch_url provider=jina url=%r", url)
        return result
    logger.warning("fetch_url provider=none url=%r", url)
    return None


async def search_web(query: str) -> str:
    result = await _hound_search(query)
    if result:
        logger.info("search_web provider=hound query=%r", query)
        return result
    result = await _jina_deepsearch(query)
    if result:
        logger.info("search_web provider=jina_deepsearch query=%r", query)
        return result
    result = await _jina_search(query)
    if result:
        logger.info("search_web provider=jina_search query=%r", query)
        return result
    result = await _serper_search(query)
    if result:
        logger.info("search_web provider=serper query=%r", query)
        return result
    result = await _ddg_search(query)
    if result:
        logger.info("search_web provider=duckduckgo query=%r", query)
        return result
    logger.warning("search_web provider=none query=%r", query)
    return "No search results found."
