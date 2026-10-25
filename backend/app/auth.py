"""Серверная авторизация: подписанные Bearer-токены без внешних зависимостей."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from .config import get_settings
from .schemas import AuthUser

TOKEN_TTL_SECONDS = 12 * 60 * 60


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _secret() -> bytes:
    return get_settings().auth_secret.encode("utf-8")


def create_access_token(*, username: str, profile_type: str, company_inn: str | None) -> str:
    payload = {
        "sub": username,
        "profile_type": profile_type,
        "company_inn": company_inn,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def decode_access_token(token: str) -> AuthUser:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_b64decode(body))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Некорректный или истёкший токен") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="Срок действия токена истёк")
    profile_type = payload.get("profile_type")
    if profile_type not in ("business", "employee"):
        raise HTTPException(status_code=401, detail="Некорректный профиль пользователя")

    return AuthUser(
        username=str(payload.get("sub") or ""),
        profile_type=profile_type,
        company_inn=payload.get("company_inn"),
    )


def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    token = authorization[7:].strip()
    user = decode_access_token(token)
    if not user.username:
        raise HTTPException(status_code=401, detail="Некорректный токен")
    return user


def require_employee(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if user.profile_type != "employee":
        raise HTTPException(status_code=403, detail="Действие доступно только сотруднику банка")
    return user


def require_business(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if user.profile_type != "business":
        raise HTTPException(status_code=403, detail="Действие доступно только предпринимателю")
    if not user.company_inn:
        raise HTTPException(status_code=403, detail="У пользователя не привязана компания")
    return user
