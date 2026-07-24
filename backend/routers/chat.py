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
            "description": "Fetch public posts or profile info from any social media platform: X/Twitter, Facebook, Instagram, Reddit, YouTube, TikTok, LinkedIn, etc. Provide the full profile URL. Uses Jina Reader to extract the page as clean text; for X/Twitter specifically, falls back to web search if Jina can't extract posts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL of the social profile or page (e.g., https://x.com/username, https://facebook.com/page, https://reddit.com/r/subreddit)",
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
            "description": "Search the web broadly for current information about any topic, person, news, event, or public figure. Uses DuckDuckGo, Jina Search, and Serper as fallback chain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The web search query string",
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
    "Your job is to answer questions about the user's connected sources, search the web or "
    "social media when asked, and explain how Vigil works.\n\n"

    # ── What Vigil is ──
    "Vigil monitors messages from sources the user has connected. Currently supported: "
    "Telegram (bot joins groups/chats and streams messages) and X/Twitter (watcher polls "
    "profiles for new posts). Incoming messages are scored by importance (1-10); HIGH-scoring "
    "alerts (≥8) are spoken aloud via TTS. Scheduled daily digests summarize important messages. "
    "Users interact via a web dashboard (live WebSocket feed) or the voice assistant "
    "(speech → LLM → TTS response).\n\n"

    # ── How data flows into Vigil ──
    "Vigil has TWO kinds of data:\n"
    "  1. PASSIVELY MONITORED (appears in 'Current data' context):\n"
    "     - Telegram messages from groups/chats the bot has joined\n"
    "     - X/Twitter posts from watched profiles (periodically polled)\n"
    "  2. ON-DEMAND SEARCH (tools you can call):\n"
    "     - search_social(url): fetch any public social profile/page via Jina Reader\n"
    "       (X, Facebook, Reddit, Instagram, YouTube, etc.)\n"
    "     - search_web(query): general web search via DuckDuckGo + Jina + Serper\n\n"

    # ── Context data format ──
    "Context format: [IMPORTANCE] source/#group/@sender: message text\n"
    "  IMPORTANCE labels: HIGH (score ≥8), MEDIUM (5-7), low (≤4)\n"
    "  source: telegram, twitter, etc.\n"
    "  #group: the group/chat/channel name\n"
    "  @sender: the sender's username\n\n"

    # ── How to handle queries ──
    "WHEN THE USER ASKS A QUESTION, IDENTIFY THE INTENT:\n\n"

    "A) 'my Telegram messages' / 'what did [person] say in Telegram' / 'my groups':\n"
    "  → This refers to the user's connected Telegram sources.\n"
    "  Look in the 'Current data' for messages tagged 'telegram/...'.\n"
    "  NEVER use search_web or search_social for Telegram — Telegram messages are private\n"
    "  and stored locally in Vigil, not on the public web.\n"
    "  If no matching messages exist: 'No Telegram messages match that in your history.'\n\n"

    "B) 'on X' / 'on Twitter' / 'what is [handle] posting' / 'check [profile]':\n"
    "  → Use search_social with the profile URL (e.g., https://x.com/handle).\n"
    "  This calls Jina Reader which extracts the page as text; for X it falls back\n"
    "  to web search if posts aren't visible. search_social also works for Facebook,\n"
    "  Reddit, Instagram, YouTube, TikTok, LinkedIn, etc.\n\n"

    "C) 'search the web' / 'find info about' / 'news about' / 'what is [topic]':\n"
    "  → Use search_web with a search query.\n\n"

    "D) 'how does Vigil work' / 'what sources do I have' / 'my watchers' / 'alerts':\n"
    "  → Answer from your knowledge of the platform. Check 'Current data' for context\n"
    "  about monitoring targets. Do NOT call any tool.\n\n"

    "E) 'what's new' / 'summarize' / 'recent messages':\n"
    "  → Read the 'Current data' section and summarize what's there. Do NOT call tools.\n\n"

    # ── Tool details for accurate reasoning ──
    "TOOL INTERNALS (for accurate answers):\n"
    "  - search_social(url): Jina Reader fetches the URL as clean text. If the URL is\n"
    "    an X/Twitter profile and Jina returns only profile metadata (not actual posts),\n"
    "    it automatically falls back to a web search for 'site:x.com username'.\n"
    "    Works best with explicit profile URLs like https://x.com/username.\n"
    "  - search_web(query): tries DuckDuckGo first, then Jina Search, then Serper.\n\n"

    # ── Voice / TTS mode ──
    "If the user is using voice (speaking), keep responses short and conversational — "
    "they will be read aloud by TTS. Avoid lists, markdown, or symbols. One paragraph max.\n\n"

    # ── Behavior rules ──
    "- Answer directly and concisely.\n"
    "- If context or search has no relevant data, say so honestly. Do not invent.\n"
    "- If a tool rate-limits or fails, tell the user clearly.\n"
    "- Distinguish between 'your monitored sources' (passive context data) and "
    "'what I can search right now' (tools). They are separate systems."
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
