from __future__ import annotations

import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from core.database import db, now_iso

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")
JWT_SECRET = os.environ.get("JWT_SECRET", "estatex_super_secret_jwt_key_32_bytes_long_2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


# ---------- Crypto & Token Helpers ----------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=JWT_EXPIRATION_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


# ---------- Pydantic Schemas ----------


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str = "agent"
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Dependencies ----------


async def require_admin(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> bool:
    """Guard destructive and expensive routes.

    Deliberately fails closed: with no ``ADMIN_TOKEN`` configured, admin routes
    are unreachable rather than open. A public deploy therefore starts read-only.
    """
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(
            401,
            "Admin routes are locked because ADMIN_TOKEN is not set on the server.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "Invalid or missing X-Admin-Token")
    return True


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserOut:
    if not creds or not creds.credentials:
        raise HTTPException(401, "Not authenticated")
    payload = decode_access_token(creds.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(401, "Invalid or expired session token")
    user_doc = await db.users.find_one({"email": payload["sub"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(401, "User not found")
    return UserOut(
        id=user_doc["id"],
        name=user_doc.get("name", "Agent"),
        email=user_doc["email"],
        role=user_doc.get("role", "agent"),
        created_at=user_doc.get("created_at", now_iso()),
    )


# ---------- Endpoints ----------


@router.post("/register", response_model=AuthResponse)
async def register(payload: UserRegister):
    email_clean = payload.email.lower().strip()
    existing = await db.users.find_one({"email": email_clean})
    if existing:
        raise HTTPException(400, "An account with this email already exists")

    user_id = str(uuid.uuid4())
    ts = now_iso()
    user_doc = {
        "id": user_id,
        "name": payload.name.strip(),
        "email": email_clean,
        "hashed_password": hash_password(payload.password),
        "role": "agent",
        "created_at": ts,
    }
    await db.users.insert_one(user_doc)

    token = create_access_token({"sub": email_clean, "uid": user_id, "name": user_doc["name"]})
    return AuthResponse(
        access_token=token,
        user=UserOut(
            id=user_id,
            name=user_doc["name"],
            email=email_clean,
            role="agent",
            created_at=ts,
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: UserLogin):
    email_clean = payload.email.lower().strip()
    user_doc = await db.users.find_one({"email": email_clean})
    if not user_doc or not verify_password(payload.password, user_doc.get("hashed_password", "")):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token({"sub": email_clean, "uid": user_doc["id"], "name": user_doc.get("name", "Agent")})
    return AuthResponse(
        access_token=token,
        user=UserOut(
            id=user_doc["id"],
            name=user_doc.get("name", "Agent"),
            email=email_clean,
            role=user_doc.get("role", "agent"),
            created_at=user_doc.get("created_at", now_iso()),
        ),
    )


@router.get("/me", response_model=UserOut)
async def me(user: UserOut = Depends(get_current_user)):
    return user

