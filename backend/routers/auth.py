import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

TOKENS: dict[str, dict] = {}
TOKEN_EXPIRY_HOURS = 24

SIGNED_TOKEN_SECRET = secrets.token_hex(32)


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: str


def _make_token() -> str:
    raw = secrets.token_urlsafe(48)
    expiry = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)
    sig = hmac.new(
        SIGNED_TOKEN_SECRET.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()[:12]
    token = f"vgl_{raw}_{sig}"
    TOKENS[token] = {"expires_at": expiry}
    return token


def verify_token(authorization: str | None = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization format")
    entry = TOKENS.get(token)
    if not entry:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if entry["expires_at"] < datetime.now(timezone.utc):
        TOKENS.pop(token, None)
        raise HTTPException(status_code=401, detail="Token expired")
    return {"token": token, "expires_at": entry["expires_at"]}


@router.post("/login")
def login(body: LoginRequest):
    from backend.config import settings

    if not hmac.compare_digest(body.password, settings.auth_password):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = _make_token()
    return LoginResponse(
        token=token,
        expires_at=TOKENS[token]["expires_at"].isoformat(),
    )


@router.post("/logout")
def logout(token_data: dict = Depends(verify_token)):
    TOKENS.pop(token_data["token"], None)
    return {"ok": True}


@router.get("/verify")
def check_token(token_data: dict = Depends(verify_token)):
    return {"ok": True, "expires_at": token_data["expires_at"].isoformat()}
