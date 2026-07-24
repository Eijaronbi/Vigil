import json

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.config import settings
from backend.database import get_db
from backend.jina_service import fetch_url, search_web
from backend.models import Message, MonitorTarget
from backend.routers.auth import get_current_user, User

router = APIRouter(prefix="/api/chat", tags=["chat"])

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_social",
            "description": "Fetch the latest public posts from any social media profile or public page. Works with X/Twitter, Facebook, Instagram, Reddit, YouTube, and any public URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full profile URL to fetch (e.g., https://x.com/cz_binance, https://facebook.com/username, https://reddit.com/r/subreddit)",
                    }
                },
                "required": ["url"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for current information about any topic, person, news, or event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string",
                    }
                },
                "required": ["query"],
            },
        }
    },
]


TOOL_IMPLEMENTATIONS = {
    "search_social": fetch_url,
    "search_web": search_web,
}


SYSTEM_PROMPT = (
    # ── Identity ──
    "You are Vigil's AI assistant inside a real-time cross-platform message monitor. "
    "Your job is to answer questions about what the user's monitored sources picked up, "
    "search the web or X when asked, and explain what Vigil is doing.\n\n"

    # ── Vigil platform overview ──
    "Vigil monitors Telegram (via a bot that joins groups and receives messages) and "
    "X/Twitter (via automated web searches for user profiles or keywords). "
    "It scores every incoming message by importance (1-10), speaks HIGH-scoring alerts "
    "aloud via TTS (text-to-speech), and sends scheduled daily digests. "
    "Users interact through a web dashboard with live WebSocket updates or by talking "
    "to the voice assistant (mic → speech recognition → you → TTS readout).\n\n"

    # ── Context data format ──
    "The 'Current data' section shows recent messages from the user's monitored sources. "
    "Format: [IMPORTANCE] source/#group/@sender: message text\n"
    "  - IMPORTANCE: HIGH (≥8), MEDIUM (5-7), low (≤4)\n"
    "  - source: telegram, twitter, etc.\n"
    "  - #group: the group/chat/channel name (or 'DM with Bot' for private chats)\n"
    "  - @sender: the username who sent it\n\n"

    # ── Source-specific query rules ──
    "WHEN THE USER ASKS ABOUT A SPECIFIC SOURCE, FOLLOW THESE RULES:\n"
    "  - Telegram: Look in the context data for messages tagged 'telegram/...'. "
    "Do NOT use search_web or search_social — Telegram messages are local to Vigil, "
    "not on the public web. If the context has no relevant Telegram data, say: "
    "'No Telegram messages match that in your recent history.'\n"
    "  - X/Twitter / social media: Use the 'search_social' tool to search X/Twitter. "
    "Only fall back to 'search_web' if search_social returns nothing useful.\n"
    "  - General web / news / anything else: Use 'search_web'.\n"
    "  - Vigil itself / how it works / monitoring status: Answer from "
    "your own knowledge of the platform. Do NOT call any tool.\n\n"

    # ── Tool reference ──
    "Tools available:\n"
    "  - search_web(query): general web search (DuckDuckGo + Jina + Serper fallback chain)\n"
    "  - search_social(query): X/Twitter search only\n\n"

    # ── Voice / TTS mode ──
    "If the user is speaking (voice assistant mode), keep responses very short and "
    "conversational — they will be read aloud by TTS. Avoid lists, markdown, or "
    "symbols. One paragraph max.\n\n"

    # ── Behavior rules ──
    "- Be concise. Answer directly.\n"
    "- If no relevant data exists in context or search results, say so honestly.\n"
    "- If a tool rate-limits or fails, mention it and suggest waiting or trying again.\n"
    "- Do NOT invent messages, users, or groups — only report what's in the context data."
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


def _build_context(db: Session, user_id: int) -> str:
    parts = []

    recent = (
        db.query(Message)
        .order_by(Message.timestamp.desc())
        .limit(15)
        .all()
    )
    if recent:
        parts.append("Recent messages:")
        for m in recent:
            score = m.importance_score or 0
            label = "HIGH" if score >= 8 else "MEDIUM" if score >= 5 else "low"
            group = m.group_name or "?"
            sender = m.sender or "?"
            parts.append(f"  [{label}] {m.source}/#{group}/@{sender}: {m.text[:150]}")
    else:
        parts.append("No messages received yet.")

    targets = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == user_id)
        .all()
    )
    if targets:
        parts.append("\nMonitoring targets:")
        for t in targets:
            status = "watching" if t.enabled else "paused"
            parts.append(f"  {t.source}/{t.label} ({t.target_id}) — {status}")

    return "\n".join(parts)


LLM_PROVIDERS: list[dict] | None = None


def _get_providers() -> list[dict]:
    global LLM_PROVIDERS
    if LLM_PROVIDERS is None:
        providers = []
        if settings.groq_api_key:
            providers.append({
                "name": "groq",
                "api_key": settings.groq_api_key,
                "model": settings.groq_model or "llama-3.3-70b-versatile",
                "base_url": "https://api.groq.com/openai/v1",
            })
        if settings.openrouter_api_key:
            providers.append({
                "name": "openrouter",
                "api_key": settings.openrouter_api_key,
                "model": settings.openrouter_model or "meta-llama/llama-3.2-3b-instruct:free",
                "base_url": settings.openrouter_base_url,
            })
        LLM_PROVIDERS = providers
    return LLM_PROVIDERS


async def _call_llm(
    messages: list[dict],
    tools: list | None = None,
    tool_choice: str | None = None,
) -> dict:
    providers = _get_providers()
    if not providers:
        return {"error": "No LLM provider configured"}

    last_error = ""
    for cfg in providers:
        body = {"model": cfg["model"], "messages": messages}
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{cfg['base_url'].rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {cfg['api_key']}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=90,
                )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                last_error = "rate_limited"
                continue
            last_error = f"LLM_{resp.status_code}"
        except Exception as e:
            last_error = str(e)
            continue

    return {"error": last_error}


async def _execute_tool(name: str, args: dict) -> str:
    impl = TOOL_IMPLEMENTATIONS.get(name)
    if not impl:
        return f"Error: unknown tool '{name}'"

    try:
        if name == "search_social":
            url = args.get("url", "")
            if not url:
                return "Error: missing 'url' argument"
            result = await impl(url)
            return result or "No content could be fetched from that URL."
        elif name == "search_web":
            query = args.get("query", "")
            if not query:
                return "Error: missing 'query' argument"
            return await impl(query)
        else:
            return "Tool result unavailable."
    except Exception as e:
        return f"Error executing tool '{name}': {e}"


class SearchRequest(BaseModel):
    query: str


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    source: str


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    current_user: User = Depends(get_current_user),
):
    raw = await search_web(body.query)
    results: list[SearchResult] = []
    source = "web"
    if raw and raw != "No search results found.":
        for i, block in enumerate(raw.split("\n\n")):
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


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_context(db, current_user.id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Current data:\n{context}"},
        {"role": "user", "content": body.message},
    ]

    result = await _call_llm(messages, tools=TOOLS)

    if "error" in result:
        err = result["error"]
        msg = "AI is rate-limited. Try again in a minute." if err == "rate_limited" else "AI service unavailable. Try again later."
        return ChatResponse(response=msg)

    choice = result["choices"][0]
    message = choice["message"]

    if message.get("tool_calls"):
        messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": message["tool_calls"],
        })

        for tc in message["tool_calls"]:
            fn = tc["function"]
            name = fn["name"]
            args = json.loads(fn["arguments"])
            tool_result = await _execute_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })

        final = await _call_llm(messages)
        if "error" in final:
            return ChatResponse(response=f"Here are the raw results:\n\n{tool_result[:2000]}")
        content = final["choices"][0]["message"]["content"]
        return ChatResponse(response=content)

    return ChatResponse(response=message.get("content", ""))
