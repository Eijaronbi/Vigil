import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt as pyjwt
from eth_account.messages import encode_defunct
from eth_account import Account
from fastapi import APIRouter, Depends, HTTPException, Header
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

NONCES: dict[str, dict] = {}
NONCE_EXPIRY_SECONDS = 300

PASSWORD_MIN = 8
PASSWORD_MAX = 128


def _jwt_secret() -> str:
    if settings.jwt_secret_key:
        return settings.jwt_secret_key
    raise RuntimeError("JWT_SECRET_KEY not configured")


def _make_jwt(user_id: int, wallet_address: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expire_hours),
    }
    if wallet_address:
        payload["wallet"] = wallet_address
    return pyjwt.encode(payload, _jwt_secret(), algorithm=settings.jwt_algorithm)


def verify_token(authorization: str | None = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization format")
    try:
        payload = pyjwt.decode(
            token, _jwt_secret(), algorithms=[settings.jwt_algorithm]
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {
        "user_id": int(payload["sub"]),
        "expires_at": datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        "wallet": payload.get("wallet"),
    }


def get_current_user(
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db),
) -> User:
    user = db.query(User).filter(User.id == token_data["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "auth_method": user.auth_method,
        "email_verified": user.email_verified,
        "wallet_address": user.wallet_address,
        "telegram_chat_id": user.telegram_chat_id,
        "created_at": user.created_at.isoformat(),
    }


# ── Request / Response models ──


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < PASSWORD_MIN:
            raise ValueError(f"Password must be at least {PASSWORD_MIN} characters")
        if len(v) > PASSWORD_MAX:
            raise ValueError(f"Password must be at most {PASSWORD_MAX} characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class NonceRequest(BaseModel):
    address: str


class NonceResponse(BaseModel):
    nonce: str
    address: str


class WalletLoginRequest(BaseModel):
    address: str
    signature: str
    nonce: str


class AuthResponse(BaseModel):
    token: str
    user: dict


# ── Email / Password ──


@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = bcrypt.hashpw(
        body.password.encode(), bcrypt.gensalt()
    ).decode()

    user = User(
        name=body.name,
        email=body.email,
        password_hash=password_hash,
        auth_method="password",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = _make_jwt(user.id)
    return AuthResponse(token=token, user=_user_to_dict(user))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _make_jwt(user.id)
    return AuthResponse(token=token, user=_user_to_dict(user))


# ── Google OAuth ──


@router.post("/google", response_model=AuthResponse)
def google_login(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    try:
        info = google_id_token.verify_oauth2_token(
            body.id_token,
            google_requests.Request(),
            settings.google_oauth_client_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {e}")

    google_id = info.get("sub")
    email = info.get("email", "")
    name = info.get("name", email.split("@")[0] or "User")

    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    user = db.query(User).filter(
        (User.google_id == google_id) | (User.email == email)
    ).first()

    if user:
        if not user.google_id:
            user.google_id = google_id
        if not user.email_verified:
            user.email_verified = True
        db.commit()
    else:
        user = User(
            name=name,
            email=email,
            google_id=google_id,
            auth_method="google",
            email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = _make_jwt(user.id)
    return AuthResponse(token=token, user=_user_to_dict(user))


# ── Wallet ──


@router.post("/nonce", response_model=NonceResponse)
def get_nonce(body: NonceRequest):
    address = body.address.lower()
    nonce = secrets.token_hex(16)
    NONCES[address] = {
        "nonce": nonce,
        "expires_at": time.time() + NONCE_EXPIRY_SECONDS,
    }
    return NonceResponse(nonce=nonce, address=address)


@router.post("/wallet-login", response_model=AuthResponse)
def wallet_login(body: WalletLoginRequest, db: Session = Depends(get_db)):
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

    user = db.query(User).filter(User.wallet_address == address).first()
    if user:
        token = _make_jwt(user.id, address)
    else:
        user = User(
            name=address[:10],
            email=f"wallet-{address[:8]}@vigil.local",
            wallet_address=address,
            auth_method="wallet",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = _make_jwt(user.id, address)

    return AuthResponse(token=token, user=_user_to_dict(user))


@router.post("/connect-wallet")
def connect_wallet(
    body: WalletLoginRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    address = body.address.lower()
    nonce_data = NONCES.pop(address, None)
    if not nonce_data:
        raise HTTPException(status_code=400, detail="No nonce requested")
    if time.time() > nonce_data["expires_at"]:
        raise HTTPException(status_code=400, detail="Nonce expired")
    if body.nonce != nonce_data["nonce"]:
        raise HTTPException(status_code=400, detail="Invalid nonce")

    message = f"Vigil\nAddress: {address}\nNonce: {nonce_data['nonce']}"
    message_hash = encode_defunct(text=message)
    recovered = Account.recover_message(message_hash, signature=body.signature)
    if recovered.lower() != address:
        raise HTTPException(status_code=401, detail="Signature does not match address")

    current_user.wallet_address = address
    db.commit()
    return {"ok": True, "wallet_address": address}


# ── Admin (master password login — no Google OAuth needed) ──


@router.post("/admin-login", response_model=AuthResponse)
def admin_login(body: dict, db: Session = Depends(get_db)):
    master = settings.auth_password
    if not master:
        raise HTTPException(status_code=503, detail="Admin password not configured")

    import hmac
    provided = body.get("password", "")
    if not provided or not hmac.compare_digest(provided.encode(), master.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin password")

    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(
            id=1,
            name="admin",
            email="admin@vigil.local",
            password_hash=bcrypt.hashpw(master.encode(), bcrypt.gensalt()).decode(),
            auth_method="password",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.password_hash or not bcrypt.checkpw(master.encode(), user.password_hash.encode()):
            user.password_hash = bcrypt.hashpw(master.encode(), bcrypt.gensalt()).decode()
            db.commit()

    token = _make_jwt(user.id)
    return AuthResponse(token=token, user=_user_to_dict(user))


# ── Config ──


@router.get("/config")
def auth_config():
    return {
        "google_oauth_client_id": settings.google_oauth_client_id,
    }


# ── Session ──


@router.post("/logout")
def logout(token_data: dict = Depends(verify_token)):
    return {"ok": True}


@router.get("/verify")
def check_token(token_data: dict = Depends(verify_token)):
    return {
        "ok": True,
        "expires_at": token_data["expires_at"].isoformat(),
        "wallet": token_data.get("wallet"),
        "user_id": token_data["user_id"],
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return _user_to_dict(current_user)
