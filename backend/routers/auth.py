import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from eth_account.messages import encode_defunct
from eth_account import Account
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

TOKENS: dict[str, dict] = {}
NONCES: dict[str, dict] = {}
TOKEN_EXPIRY_HOURS = 24
NONCE_EXPIRY_SECONDS = 300

SIGNED_TOKEN_SECRET = secrets.token_hex(32)


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: str


class NonceRequest(BaseModel):
    address: str


class NonceResponse(BaseModel):
    nonce: str
    address: str


class WalletLoginRequest(BaseModel):
    address: str
    signature: str
    nonce: str


class WalletLoginResponse(BaseModel):
    token: str
    expires_at: str
    address: str


def _make_token(wallet_address: str | None = None) -> str:
    raw = secrets.token_urlsafe(48)
    expiry = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)
    sig = hmac.new(
        SIGNED_TOKEN_SECRET.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()[:12]
    token = f"vgl_{raw}_{sig}"
    TOKENS[token] = {"expires_at": expiry, "address": wallet_address}
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
    return {"token": token, "expires_at": entry["expires_at"], "address": entry.get("address")}


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


@router.post("/nonce")
def get_nonce(body: NonceRequest):
    address = body.address.lower()
    nonce = secrets.token_hex(16)
    NONCES[address] = {
        "nonce": nonce,
        "expires_at": time.time() + NONCE_EXPIRY_SECONDS,
    }
    return NonceResponse(nonce=nonce, address=address)


@router.post("/wallet-login")
def wallet_login(body: WalletLoginRequest):
    address = body.address.lower()
    nonce_data = NONCES.pop(address, None)
    if not nonce_data:
        raise HTTPException(status_code=400, detail="No nonce requested")
    if time.time() > nonce_data["expires_at"]:
        raise HTTPException(status_code=400, detail="Nonce expired")
    if body.nonce != nonce_data["nonce"]:
        raise HTTPException(status_code=400, detail="Invalid nonce")

    message = f"Vigil\nAddress: {address}\nNonce: {nonce_data['nonce']}"
    try:
        message_hash = encode_defunct(text=message)
        recovered = Account.recover_message(message_hash, signature=body.signature)
        if recovered.lower() != address:
            raise HTTPException(status_code=401, detail="Signature does not match address")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Signature verification failed: {e}")

    token = _make_token(address)
    return WalletLoginResponse(
        token=token,
        expires_at=TOKENS[token]["expires_at"].isoformat(),
        address=address,
    )


@router.post("/logout")
def logout(token_data: dict = Depends(verify_token)):
    TOKENS.pop(token_data["token"], None)
    return {"ok": True}


@router.get("/verify")
def check_token(token_data: dict = Depends(verify_token)):
    return {
        "ok": True,
        "expires_at": token_data["expires_at"].isoformat(),
        "address": token_data.get("address"),
    }
