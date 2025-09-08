import os, uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
import jwt
from passlib.context import CryptContext
from fastapi import Request, HTTPException

SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_MIN = int(os.getenv("ACCESS_TOKEN_MIN", "10"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def hash_password(p: str) -> str:
    return pwd_context.hash(p)

def verify_password(p: str, h: str) -> bool:
    return pwd_context.verify(p, h)

def create_access_token(sub: str, token_version: str = "0") -> str:
    exp = utcnow() + timedelta(minutes=ACCESS_TOKEN_MIN)
    payload = {"sub": sub, "type": "access", "exp": exp, "iat": utcnow(), "ver": token_version}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(sub: str, token_version: str = "0") -> Tuple[str, str]:
    exp = utcnow() + timedelta(days=REFRESH_TOKEN_DAYS)
    jti = str(uuid.uuid4())
    payload = {"sub": sub, "type": "refresh", "jti": jti, "exp": exp, "iat": utcnow(), "ver": token_version}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def set_auth_cookies(resp, access: str, refresh: str, csrf: str):
    common = dict(samesite="lax", secure=COOKIE_SECURE, domain=COOKIE_DOMAIN)
    resp.set_cookie("access_token", access, httponly=True, **common)
    resp.set_cookie("refresh_token", refresh, httponly=True, **common)
    # readable CSRF token for SPA (double-submit)
    resp.set_cookie("csrf_token", csrf, httponly=False, **common)

def clear_auth_cookies(resp):
    for name in ("access_token", "refresh_token", "csrf_token"):
        resp.delete_cookie(name, domain=COOKIE_DOMAIN, samesite="lax")

def require_csrf(request: Request):
    # Enforce only on state-changing methods
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        header = request.headers.get("X-CSRF-Token")
        cookie = request.cookies.get("csrf_token")
        if not header or not cookie or header != cookie:
            raise HTTPException(status_code=403, detail="CSRF validation failed")