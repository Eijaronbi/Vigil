import httpx

from backend.config import settings

JINA_READER_URL = "https://r.jina.ai"
JINA_SEARCH_URL = "https://s.jina.ai"
TIMEOUT = 30


def _headers() -> dict:
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
                headers=_headers(),
                json={"url": url},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            content = data.get("data", {}).get("content", "")
            return content.strip() if content else None
    except Exception:
        return None


async def search_web(query: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                JINA_SEARCH_URL,
                headers=_headers(),
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
