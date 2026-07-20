import httpx

from backend.config import settings

JINA_READER_URL = "https://r.jina.ai"
JINA_SEARCH_URL = "https://s.jina.ai"
SERPER_URL = "https://google.serper.dev/search"
TIMEOUT = 30


# ── Jina Reader (social media / URL content fetch) ──


def _jina_headers() -> dict:
    headers = {"Accept": "application/json"}
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"
    return headers


async def fetch_url(url: str) -> str | None:
    full_url = f"{JINA_READER_URL}/{url}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                full_url,
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


# ── Web Search (Serper → DuckDuckGo → Jina) ──


async def _serper_search(query: str) -> list[dict] | None:
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
                    "content": item.get("snippet", "")[:500],
                })
            return results if results else None
    except Exception:
        return None


async def _ddg_search(query: str) -> list[dict]:
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", "")[:500],
                })
        return results
    except Exception:
        return []


async def _jina_search(query: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                JINA_SEARCH_URL,
                headers=_jina_headers(),
                json={"q": query},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = []
            for item in data.get("data", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", "")[:500],
                })
            return results
    except Exception:
        return []


async def search_web(query: str) -> list[dict]:
    results = await _serper_search(query)
    if results:
        return results
    results = await _ddg_search(query)
    if results:
        return results
    return await _jina_search(query)
