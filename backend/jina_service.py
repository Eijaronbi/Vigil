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


# ── Jina Reader (fetch any public URL as clean text) ──


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


# ── Web Search (Jina Search → Jina DeepSearch → Serper → DuckDuckGo) ──


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
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Vigil/1.0)",
                },
            )
            if resp.status_code != 200:
                return None
            results = []
            import re
            for item in re.findall(
                r'<a rel="nofollow" class="result__a" href="([^"]+)".*?>(.*?)</a>.*?'
                r'<a class="result__snippet"[^>]*>(.*?)</a>',
                resp.text,
                re.DOTALL,
            ):
                href, title_html, snippet_html = item
                import html as hlib
                title = hlib.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
                snippet = hlib.unescape(re.sub(r"<[^>]+>", "", snippet_html)).strip()
                results.append({
                    "title": title,
                    "url": href,
                    "content": snippet,
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
    import re
    x_match = re.match(r"https?://(?:www\.)?(?:x|twitter)\.com/([a-zA-Z0-9_]+)", url)

    result = await _jina_reader(url)

    if x_match:
        username = x_match.group(1)
        search_result = await search_web(f"site:x.com {username}")
        if search_result and "No search results found." not in search_result and len(search_result) > 100:
            return f"Profile: {url}\n\nRecent posts from @{username}:\n{search_result}"

    if result and len(result) > 200:
        return result

    logger.warning("fetch_url provider=none url=%r", url)
    return None


async def search_web(query: str) -> str:
    result = await _ddg_search(query)
    if result:
        return result
    result = await _jina_search(query)
    if result:
        return result
    result = await _jina_deepsearch(query)
    if result:
        return result
    result = await _serper_search(query)
    if result:
        return result
    logger.warning("search_web provider=none query=%r", query)
    return "No search results found."
