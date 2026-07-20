import json

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.classifier.llm_scorer import LLMScorer
from backend.config import settings
from backend.database import get_db
from backend.models import Message, MonitorTarget
from backend.routers.auth import verify_token

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


def _get_scorer():
    if settings.groq_api_key:
        return LLMScorer(
            api_key=settings.groq_api_key,
            model="llama-3.3-70b-versatile",
        )
    return LLMScorer(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model or "meta-llama/llama-3.2-3b-instruct:free",
        base_url=settings.openrouter_base_url,
    )


def _build_context(db: Session) -> str:
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
            parts.append(f"  [{label}] {m.source}/{m.sender}: {m.text[:150]}")
    else:
        parts.append("No messages received yet.")

    targets = (
        db.query(MonitorTarget)
        .filter(MonitorTarget.user_id == 1)
        .all()
    )
    if targets:
        parts.append("\nMonitoring targets:")
        for t in targets:
            status = "watching" if t.enabled else "paused"
            parts.append(f"  {t.source}/{t.label} ({t.target_id}) — {status}")

    return "\n".join(parts)


SYSTEM_PROMPT = (
    "You are Vigil's AI assistant inside a cross-platform message monitor."
    " The user has connected Telegram, X/Twitter, Facebook, and other sources."
    " Below is their recent message feed and monitoring targets."
    " Answer questions about what's happening, who posted what,"
    " and help them track important messages and job opportunities."
    " Be concise. If asked about a specific person or topic,"
    " check the message feed for relevant content."
    " If there's no relevant data, say so honestly."
)


@router.post("")
async def chat(body: ChatRequest, db: Session = Depends(get_db), _=Depends(verify_token)):
    context = _build_context(db)
    scorer = _get_scorer()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            scorer.api_url,
            headers={
                "Authorization": f"Bearer {scorer.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": scorer.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "system", "content": f"Current data:\n{context}"},
                    {"role": "user", "content": body.message},
                ],
            },
            timeout=60,
        )

    if response.status_code != 200:
        return {"response": "AI is unavailable right now. Try again later."}

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return {"response": content}
