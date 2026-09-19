"""口令登录鉴权：环境变量 APP_PASSWORD（未设默认 admin123），HMAC 签名 cookie。"""
import os
import secrets

from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from starlette.middleware.base import BaseHTTPMiddleware

import db
from db import DATA_DIR

COOKIE_NAME = "fk_session"
MAX_AGE = 7 * 24 * 3600
_SECRET_FILE = DATA_DIR / "secret.key"


def _secret() -> bytes:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _SECRET_FILE.exists():
        _SECRET_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
    return _SECRET_FILE.read_text(encoding="utf-8").strip().encode()


def make_token() -> str:
    return TimestampSigner(_secret()).sign(b"ok").decode()


def verify_token(token: str) -> bool:
    if not token:
        return False
    try:
        TimestampSigner(_secret()).unsign(token, max_age=MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def current_password() -> str:
    return os.environ.get("APP_PASSWORD") or "admin123"


def is_default_password() -> bool:
    return "APP_PASSWORD" not in os.environ


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith("/api") and path != "/api/login":
            if not verify_token(request.cookies.get(COOKIE_NAME)):
                return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)
        return await call_next(request)


def init_secret():
    db.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _secret()
