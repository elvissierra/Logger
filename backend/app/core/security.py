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


# Symmetric key for JWT signing; keep secret in prod (env).
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
ALGORITHM = "HS256"
# Short-lived access tokens; refresh flow issues a new access token when needed.
ACCESS_TOKEN_MIN = int(os.getenv("ACCESS_TOKEN_MIN", "10"))
# Longer-lived refresh token rotation window.
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
# Cookie attributes affect browser storage & sending behavior across subdomains/schemes.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None

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
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def set_auth_cookies(resp, access: str, refresh: str, csrf: str):
    """
    Set httpOnly access/refresh cookies and a readable csrf_token for SPA requests.
    SameSite is configurable; for cross-site embeds, use SameSite=None and secure cookies over HTTPS.
    """
    common = dict(samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE, domain=COOKIE_DOMAIN)
    resp.set_cookie("access_token", access, httponly=True, **common)
    resp.set_cookie("refresh_token", refresh, httponly=True, **common)
    # readable CSRF token for SPA (double-submit)
    resp.set_cookie("csrf_token", csrf, httponly=False, **common)


def clear_auth_cookies(resp):
    for name in ("access_token", "refresh_token", "csrf_token"):
        resp.delete_cookie(name, domain=COOKIE_DOMAIN, samesite=COOKIE_SAMESITE)


def require_csrf(request: Request):
    """Double-submit CSRF guard; raises 403 if header/cookie mismatch on mutating requests."""
    # Enforce only on state-changing methods
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        header = request.headers.get("X-CSRF-Token")
        cookie = request.cookies.get("csrf_token")
        if not header or not cookie or header != cookie:
            raise HTTPException(status_code=403, detail="CSRF validation failed")
