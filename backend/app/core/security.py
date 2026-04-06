"""
Security helpers (Knowledge Drop)

What this file does
- Password hashing/verification, JWT creation/verification, and auth cookie management for a SPA using cookie-based auth.

How it collaborates
- Routes call create_*_token() and set_auth_cookies() during login/refresh; decode_token() is used by auth guards.
- CSRF is enforced for state-changing requests with the double-submit pattern (csrf_token cookie + X-CSRF-Token header).

Why necessary
- Centralizes security choices (algorithms, lifetimes, cookie flags) so changes are consistent across the app.

Notes
- COOKIE_SECURE=1 and SameSite=None require HTTPS; in dev we keep SameSite=Lax with secure=False.
- Rotating refresh tokens should go with server-side revocation/RT hash matching (see User.refresh_token_hash / refresh_jti).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple
import jwt
from passlib.context import CryptContext
from fastapi import Request, HTTPException


# Symmetric key for JWT signing; MUST be set via env outside of dev.
# In dev (APP_ENV=dev), if unset we generate an ephemeral random key per process so
# tokens are still valid for the lifetime of the server but won't survive a restart.
# In any non-dev environment, missing/weak SECRET_KEY is a hard startup error —
# a leaked default would let anyone mint valid tokens.
APP_ENV = os.getenv("APP_ENV", "dev").strip().lower()
_SECRET_FROM_ENV = os.getenv("SECRET_KEY", "").strip()
_WEAK_SECRETS = {"", "dev-change-me", "change-me-very-long-random", "changeme", "secret"}

if _SECRET_FROM_ENV in _WEAK_SECRETS or len(_SECRET_FROM_ENV) < 32:
    if APP_ENV != "dev":
        raise RuntimeError(
            "SECRET_KEY is missing or too weak. Set SECRET_KEY (>=32 chars) in the "
            "environment before starting the API in non-dev mode. Generate one with: "
            "python3 -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    import secrets as _secrets
    SECRET_KEY = _secrets.token_urlsafe(64)
    import logging as _logging
    _logging.getLogger("uvicorn.error").warning(
        "[security] SECRET_KEY not set or weak; using ephemeral dev key. "
        "Tokens will be invalidated on next restart."
    )
else:
    SECRET_KEY = _SECRET_FROM_ENV

ALGORITHM = "HS256"

# JWT iss/aud claims — bind tokens to this service so they can't be replayed elsewhere.
JWT_ISSUER = os.getenv("JWT_ISSUER", "logger-api")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "logger-spa")

def _int_env(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default

ACCESS_TOKEN_MIN = _int_env("ACCESS_TOKEN_MIN", 10)
REFRESH_TOKEN_DAYS = _int_env("REFRESH_TOKEN_DAYS", 14)

# Cookie attributes affect browser storage & sending behavior across subdomains/schemes.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None

# __Host- prefix cookies are the gold standard for first-party auth: browser enforces
# Secure + Path=/ + no Domain. We can only use them when COOKIE_SECURE=1 AND no
# explicit domain is set (host-only). Otherwise fall back to plain names.
_CAN_USE_HOST_PREFIX = COOKIE_SECURE and not COOKIE_DOMAIN
_PFX = "__Host-" if _CAN_USE_HOST_PREFIX else ""
ACCESS_COOKIE = f"{_PFX}access_token"
REFRESH_COOKIE = f"{_PFX}refresh_token"
CSRF_COOKIE = f"{_PFX}csrf_token"

# Determine SameSite mode for cookies (configurable, defaults by environment)
_COOKIE_SAMESITE_ENV = os.getenv("COOKIE_SAMESITE")
if _COOKIE_SAMESITE_ENV:
    _samesite = _COOKIE_SAMESITE_ENV.strip().lower()
    if _samesite not in ("lax", "none", "strict"):
        _samesite = "lax"
    COOKIE_SAMESITE = _samesite
else:
    # If secure, default to 'none' (for cross-site); else 'lax'
    COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(p: str) -> str:
    return pwd_context.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd_context.verify(p, h)


def create_access_token(sub: str, token_version: str = "0") -> str:
    exp = utcnow() + timedelta(minutes=ACCESS_TOKEN_MIN)
    payload = {
        "sub": sub,
        "type": "access",
        "exp": exp,
        "iat": utcnow(),
        "ver": token_version,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(sub: str, token_version: str = "0") -> Tuple[str, str]:
    exp = utcnow() + timedelta(days=REFRESH_TOKEN_DAYS)
    jti = str(uuid.uuid4())
    payload = {
        "sub": sub,
        "type": "refresh",
        "jti": jti,
        "exp": exp,
        "iat": utcnow(),
        "ver": token_version,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def set_auth_cookies(resp, access: str, refresh: str, csrf: str):
    access_max_age = ACCESS_TOKEN_MIN * 60
    refresh_max_age = REFRESH_TOKEN_DAYS * 24 * 60 * 60

    # When using __Host- prefix, the browser rejects the cookie if Domain is set.
    common = dict(
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        domain=None if _CAN_USE_HOST_PREFIX else COOKIE_DOMAIN,
        path="/",
    )

    resp.set_cookie(
        ACCESS_COOKIE,
        access,
        httponly=True,
        max_age=access_max_age,
        expires=access_max_age,
        **common,
    )
    resp.set_cookie(
        REFRESH_COOKIE,
        refresh,
        httponly=True,
        max_age=refresh_max_age,
        expires=refresh_max_age,
        **common,
    )
    resp.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        max_age=refresh_max_age,
        expires=refresh_max_age,
        **common,
    )


def clear_auth_cookies(resp):
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        resp.delete_cookie(
            name,
            domain=None if _CAN_USE_HOST_PREFIX else COOKIE_DOMAIN,
            samesite=COOKIE_SAMESITE,
            path="/",
        )


def require_csrf(request: Request):
    """Double-submit CSRF guard; raises 403 if header/cookie mismatch on mutating requests."""
    # Enforce only on state-changing methods
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        header = request.headers.get("X-CSRF-Token")
        cookie = request.cookies.get(CSRF_COOKIE)
        if not header or not cookie or header != cookie:
            raise HTTPException(status_code=403, detail="CSRF validation failed")
