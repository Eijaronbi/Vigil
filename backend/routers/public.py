from fastapi import APIRouter
from pydantic import BaseModel

from backend.jina_service import search_web, fetch_url

router = APIRouter(prefix="/api/public", tags=["public"])


class SearchRequest(BaseModel):
    query: str


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    source: str


class FetchRequest(BaseModel):
    url: str


class FetchResponse(BaseModel):
    content: str


@router.post("/search", response_model=SearchResponse)
async def public_search(body: SearchRequest):
    raw = await search_web(body.query)
    results: list[SearchResult] = []
    source = "web"
    if raw and raw != "No search results found.":
        for block in raw.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            title_line = lines[0] if lines else ""
            idx = title_line.find(". ")
            title = title_line[idx + 2:].strip() if idx > 0 else title_line
            url = ""
            snippet = ""
            for line in lines[1:]:
                if line.startswith("   URL: "):
                    url = line[8:].strip()
                elif line.strip() and not snippet:
                    snippet = line.strip()[:400]
            results.append(SearchResult(title=title, url=url, snippet=snippet))
    if not results:
        results.append(SearchResult(title=raw or "No results", url="", snippet=""))
    return SearchResponse(results=results[:5], source=source)


@router.get("/search", response_model=SearchResponse)
async def public_search_get(query: str):
    return await public_search(SearchRequest(query=query))


@router.post("/fetch", response_model=FetchResponse)
async def public_fetch(body: FetchRequest):
    content = await fetch_url(body.url)
    return FetchResponse(content=content or "No content could be fetched.")


@router.get("/fetch", response_model=FetchResponse)
async def public_fetch_get(url: str):
    content = await fetch_url(url)
    return FetchResponse(content=content or "No content could be fetched.")
