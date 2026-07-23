import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import httpx
import jwt as pyjwt
from eth_account.messages import encode_defunct
from eth_account import Account
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import User

logger = logging.getLogger("vigil.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

NONCES: dict[str, dict] = {}
NONCE_EXPIRY_SECONDS = 300

PASSWORD_MIN = 8
PASSWORD_MAX = 128

AUTH_METHOD_ORDER = [
    "email",
    "google",
    "github",
    "wallet",
    "admin",
]


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


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def _get_current_user_from_request(request: Request, db: Session) -> User | None:
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = pyjwt.decode(
            token, _jwt_secret(), algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("user_id") or int(payload.get("sub", 0))
        if not user_id:
            return None
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        return None


def _user_to_dict(user: User) -> dict:
    d: dict = {
        "id": user.id,
        "name": user.name,
        "auth_method": user.auth_method,
        "created_at": user.created_at.isoformat(),
    }
    if user.email:
        d["email"] = user.email
    if user.email_verified:
        d["email_verified"] = user.email_verified
    if user.google_id:
        d["google_id"] = user.google_id
    if user.github_id:
        d["github_id"] = user.github_id
    if user.wallet_address:
        d["wallet_address"] = user.wallet_address
    if user.avatar_url:
        d["avatar_url"] = user.avatar_url
    if user.telegram_chat_id:
        d["telegram_chat_id"] = user.telegram_chat_id
    return d


def _unified_login(
    db: Session,
    *,
    name: str,
    email: Optional[str] = None,
    auth_method: str,
    google_id: Optional[str] = None,
    github_id: Optional[str] = None,
    wallet_address: Optional[str] = None,
    avatar_url: Optional[str] = None,
    email_verified: bool = False,
) -> dict:
    user: User | None = None

    if auth_method == "email" and email:
        user = db.query(User).filter(User.email == email).first()
    elif auth_method == "google" and google_id:
        user = db.query(User).filter(
            (User.google_id == google_id) | (User.email == email)
        ).first() if email else db.query(User).filter(User.google_id == google_id).first()
    elif auth_method == "github" and github_id:
        user = db.query(User).filter(
            (User.github_id == github_id) | (User.email == email)
        ).first() if email else db.query(User).filter(User.github_id == github_id).first()
    elif auth_method == "wallet" and wallet_address:
        wallet_lower = wallet_address.lower()
        user = db.query(User).filter(User.wallet_address == wallet_lower).first()

    if not user:
        user = User(
            name=name,
            email=email,
            auth_method=auth_method,
            google_id=google_id,
            github_id=github_id,
            wallet_address=wallet_address.lower() if wallet_address else None,
            avatar_url=avatar_url,
            email_verified=email_verified,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Created new user id=%s via %s", user.id, auth_method)
    else:
        changed = False
        if google_id and not user.google_id:
            user.google_id = google_id
            changed = True
        if github_id and not user.github_id:
            user.github_id = github_id
            changed = True
        if wallet_address and not user.wallet_address:
            user.wallet_address = wallet_address.lower()
            changed = True
        if email and not user.email:
            user.email = email
            changed = True
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
            changed = True
        if changed:
            db.commit()
            db.refresh(user)
            logger.info("Linked provider for user id=%s", user.id)

    token = _make_jwt(user.id, user.wallet_address)
    return {"token": token, "user": _user_to_dict(user)}


# ── Request / Response models ──


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class GitHubAuthRequest(BaseModel):
    code: str


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


# ── 1. Email / Password ──


@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    if len(body.password) < PASSWORD_MIN or len(body.password) > PASSWORD_MAX:
        raise HTTPException(status_code=400, detail="Password must be 8-128 characters")

    result = _unified_login(
        db,
        name=body.name,
        email=body.email,
        auth_method="email",
        email_verified=False,
    )

    user = db.query(User).filter(User.email == body.email).first()
    user.password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    db.commit()
    result["user"] = _user_to_dict(user)
    return result


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return _unified_login(
        db,
        name=user.name,
        email=user.email,
        auth_method="email",
        email_verified=user.email_verified,
    )


# ── 2. Google OAuth ──


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
    name = info.get("name", email.split("@")[0] or "Google User")
    avatar = info.get("picture")

    if not google_id:
        raise HTTPException(status_code=401, detail="Google token missing sub")

    return _unified_login(
        db,
        name=name,
        email=email or None,
        auth_method="google",
        google_id=google_id,
        avatar_url=avatar,
        email_verified=info.get("email_verified", "true") == "true",
    )


# ── 3. GitHub OAuth ──


@router.post("/github", response_model=AuthResponse)
async def github_login(body: GitHubAuthRequest, db: Session = Depends(get_db)):
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": body.code,
            },
            headers={"Accept": "application/json"},
        )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="GitHub token exchange failed")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="GitHub did not return access token")

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=15) as client:
        user_resp = await client.get("https://api.github.com/user", headers=headers)
    if user_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to fetch GitHub user")

    gh = user_resp.json()
    github_id = str(gh.get("id"))
    name = gh.get("name") or gh.get("login") or "GitHub User"
    email = gh.get("email")
    avatar = gh.get("avatar_url")

    if not email:
        async with httpx.AsyncClient(timeout=15) as client:
            emails_resp = await client.get(
                "https://api.github.com/user/emails", headers=headers
            )
        if emails_resp.status_code == 200:
            for e in emails_resp.json():
                if e.get("primary") and e.get("verified"):
                    email = e["email"]
                    break

    return _unified_login(
        db,
        name=name,
        email=email,
        auth_method="github",
        github_id=github_id,
        avatar_url=avatar,
        email_verified=True,
    )


# ── 4. Wallet (Ethereum / EIP-191) ──


@router.post("/nonce", response_model=NonceResponse)
def get_nonce(body: NonceRequest):
    import secrets
    import time as time_module
    address = body.address.lower()
    nonce = secrets.token_hex(16)
    NONCES[address] = {
        "nonce": nonce,
        "expires_at": time_module.time() + NONCE_EXPIRY_SECONDS,
    }
    return NonceResponse(nonce=nonce, address=address)


@router.post("/wallet-login", response_model=AuthResponse)
def wallet_login(body: WalletLoginRequest, db: Session = Depends(get_db)):
    import time as time_module
    address = body.address.lower()
    nonce_data = NONCES.pop(address, None)
    if not nonce_data:
        raise HTTPException(status_code=400, detail="No nonce requested")
    if time_module.time() > nonce_data["expires_at"]:
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
        return _unified_login(
            db,
            name=user.name,
            wallet_address=address,
            auth_method="wallet",
        )

    return _unified_login(
        db,
        name=address[:10],
        wallet_address=address,
        auth_method="wallet",
    )


@router.post("/connect-wallet")
def connect_wallet(
    body: WalletLoginRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import time as time_module
    address = body.address.lower()
    nonce_data = NONCES.pop(address, None)
    if not nonce_data:
        raise HTTPException(status_code=400, detail="No nonce requested")
    if time_module.time() > nonce_data["expires_at"]:
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


# ── 5. Admin (master password) ──


@router.post("/admin-login", response_model=AuthResponse)
def admin_login(body: dict, db: Session = Depends(get_db)):
    master = settings.auth_password
    if not master:
        raise HTTPException(status_code=503, detail="Admin password not configured")
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
        "google": {
            "client_id": settings.google_oauth_client_id,
            "enabled": bool(settings.google_oauth_client_id),
        },
        "github": {
            "client_id": settings.github_oauth_client_id,
            "enabled": bool(settings.github_oauth_client_id),
        },
        "wallet": {"enabled": True},
        "admin": {"enabled": bool(settings.auth_password)},
        "email_password": {"enabled": True},
        "methods_order": AUTH_METHOD_ORDER,
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
