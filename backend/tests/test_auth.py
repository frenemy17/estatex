from __future__ import annotations

import asyncio
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from routes.auth import (
    UserLogin,
    UserRegister,
    create_access_token,
    decode_access_token,
    get_current_user,
    hash_password,
    login,
    me,
    register,
    verify_password,
)


def test_password_hashing_and_verification():
    raw = "superSecretPassword123"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("wrongPassword", hashed) is False


def test_jwt_token_roundtrip():
    payload = {"sub": "agent@estatex.io", "uid": "agent_123"}
    token = create_access_token(payload)
    assert isinstance(token, str)
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "agent@estatex.io"
    assert decoded["uid"] == "agent_123"
    assert "exp" in decoded


def test_register_and_login_flow(fake_db):
    async def _test():
        reg_payload = UserRegister(
            name="Sarah Connor",
            email="sarah.c@estatex.io",
            password="estatexSecret2026",
        )
        res = await register(reg_payload)
        assert res.access_token is not None
        assert res.user.email == "sarah.c@estatex.io"
        assert res.user.name == "Sarah Connor"

        # Duplicate registration must fail with 400
        with pytest.raises(HTTPException) as exc_info:
            await register(reg_payload)
        assert exc_info.value.status_code == 400

        # Successful login
        login_payload = UserLogin(
            email="sarah.c@estatex.io",
            password="estatexSecret2026",
        )
        login_res = await login(login_payload)
        assert login_res.access_token is not None
        assert login_res.user.id == res.user.id

        # Wrong password login must fail with 401
        bad_login = UserLogin(
            email="sarah.c@estatex.io",
            password="wrongPassword",
        )
        with pytest.raises(HTTPException) as exc_info:
            await login(bad_login)
        assert exc_info.value.status_code == 401

    asyncio.run(_test())


def test_get_current_user(fake_db):
    async def _test():
        # Register a user first
        reg = await register(
            UserRegister(
                name="John Doe",
                email="john@estatex.io",
                password="estatexPassword123",
            )
        )
        token = reg.access_token

        # Authenticated me endpoint
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        current_user = await get_current_user(creds)
        assert current_user.email == "john@estatex.io"
        assert current_user.name == "John Doe"

        # Invalid token must fail with 401
        bad_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token.here")
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(bad_creds)
        assert exc_info.value.status_code == 401

    asyncio.run(_test())
