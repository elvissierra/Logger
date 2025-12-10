"""
Knowledge Drop — app/routes/auth.py (Auth API)

What this file does
- Registration, login, refresh, revoke-all, logout, and /me endpoints backed by cookie-based JWTs.

How it works with other resources
- Uses security helpers to hash/verify passwords, mint JWTs, and set/clear cookies.
- Reads/writes user model fields for refresh rotation (hash+jti) and token versioning.

Why it’s necessary
- Provides a clean, browser-friendly auth flow that works with SPA fetch (credentials: 'include').

Notes
- /refresh rotates the refresh token on every call and stores only its hash.
- /revoke_all bumps token_version to invalidate all existing tokens at once.
- CSRF is enforced by state-changing endpoints in other routers, not here (optionally could add to logout).
"""

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.orm import Session
import secrets

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, LoginRequest, UserOut
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    set_auth_cookies,
    clear_auth_cookies,
    pwd_context,
    require_csrf,
)

router = APIRouter()


def _user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def _user_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


# Read access_token from cookies, validate/verify against user/token_version, and return the user or 401
def _verify_and_get_user_from_access(
    request: Request, db: Session = Depends(get_db)
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = _user_by_id(db, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User disabled or not found")
    # Token version check (revocation)
    token_ver = str(payload.get("ver", "0"))
    if token_ver != str(user.token_version or "0"):
        raise HTTPException(status_code=401, detail="Token version mismatch (revoked)")
    return user


# Create user, issue access/refresh cookies, store hashed refresh & jti; returns public user payload
@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, response: Response, db: Session = Depends(get_db)):
    exists = _user_by_email(db, payload.email)
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=str(payload.email), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    # issue tokens and persist refresh hash/jti
    access = create_access_token(user.id, str(user.token_version or "0"))
    refresh, jti = create_refresh_token(user.id, str(user.token_version or "0"))
    user.refresh_token_hash = pwd_context.hash(refresh)
    user.refresh_jti = jti
    db.add(user)
    db.commit()
    csrf = secrets.token_urlsafe(24)
    set_auth_cookies(response, access, refresh, csrf)
    return user


# Authenticate credentials; rotate refresh; set new cookies; returns public user payload
@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = _user_by_email(db, str(payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token(user.id, str(user.token_version or "0"))
    refresh, jti = create_refresh_token(user.id, str(user.token_version or "0"))
    user.refresh_token_hash = pwd_context.hash(refresh)
    user.refresh_jti = jti
    db.add(user)
    db.commit()
    csrf = secrets.token_urlsafe(24)
    set_auth_cookies(response, access, refresh, csrf)
    return user


# Validate refresh token (type, jti, hash, version), rotate both tokens, set cookies; returns user
@router.post("/refresh", response_model=UserOut)
def refresh(response: Response, request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = _user_by_id(db, payload.get("sub") or "")
    if not user or not user.refresh_token_hash or not user.refresh_jti:
        raise HTTPException(status_code=401, detail="Refresh invalidated")
    # Token version check (revocation)
    if str(payload.get("ver", "0")) != str(user.token_version or "0"):
        raise HTTPException(status_code=401, detail="Refresh revoked by version bump")
    # verify token matches stored hash and jti (rotation)
    if payload.get("jti") != user.refresh_jti or not pwd_context.verify(
        token, user.refresh_token_hash
    ):
        raise HTTPException(status_code=401, detail="Refresh revoked")
    # rotate
    access = create_access_token(user.id, str(user.token_version or "0"))
    refresh_new, jti_new = create_refresh_token(user.id, str(user.token_version or "0"))
    user.refresh_token_hash = pwd_context.hash(refresh_new)
    user.refresh_jti = jti_new
    db.add(user)
    db.commit()
    csrf = secrets.token_urlsafe(24)
    set_auth_cookies(response, access, refresh_new, csrf)
    return user


# Invalidate all outstanding tokens by bumping token_version; clears stored refresh state
@router.post("/revoke_all")
def revoke_all(response: Response, request: Request, db: Session = Depends(get_db)):
    user = _verify_and_get_user_from_access(request, db)
    # bump token version to invalidate all outstanding tokens
    user.token_version = str(int(str(user.token_version or "0")) + 1)
    user.refresh_token_hash = None
    user.refresh_jti = None
    db.add(user)
    db.commit()
    clear_auth_cookies(response)
    return {"ok": True}


# Clear cookies client-side and best-effort clear stored refresh state on the user
@router.post("/logout")
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    # Enforce CSRF for logout to prevent cross-site triggers
    require_csrf(request)
    clear_auth_cookies(response)
    # best effort: invalidate stored refresh
    access_user = None
    try:
        access_user = _verify_and_get_user_from_access(request, db)
    except Exception:
        pass
    if access_user:
        access_user.refresh_token_hash = None
        access_user.refresh_jti = None
        db.add(access_user)
        db.commit()
    return {"ok": True}


# Return the authenticated user derived from access token (401 if missing/invalid)
@router.get("/me", response_model=UserOut)
def me(request: Request, db: Session = Depends(get_db)):
    user = _verify_and_get_user_from_access(request, db)
    return user
