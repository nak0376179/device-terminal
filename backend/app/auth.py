"""JWT creation and FastAPI dependency for tenant authentication."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = int(os.environ.get("JWT_TTL_HOURS", "8"))


class _PwdContext:
    def hash(self, secret: str) -> str:
        return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()

    def verify(self, secret: str, hashed: str) -> bool:
        return bcrypt.checkpw(secret.encode(), hashed.encode())


pwd_context = _PwdContext()


def create_token(group_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_TTL_HOURS)
    return jwt.encode({"group_id": group_id, "exp": exp}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return str(payload["group_id"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def decode_token_raw(token: str) -> str | None:
    """Return group_id or None. For WebSocket auth where HTTPException is inappropriate."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return str(payload["group_id"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


class JWTBearer(HTTPBearer):
    async def __call__(self, request: Request) -> str:  # type: ignore[override]
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        return _decode_token(credentials.credentials)


jwt_bearer = JWTBearer()
