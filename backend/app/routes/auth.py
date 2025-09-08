from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.orm import Session
from pydantic import EmailStr
import secrets

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, LoginRequest, UserOut
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    set_auth_cookies, clear_auth_cookies, require_csrf, pwd_context
)

router = APIRouter()

def _user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

def _user_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)

def _verify_and_get_user_from_access(request: Request, db: Session) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = _user_by_id(db, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User disabled or not found")
    return user

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, response: Response, db: Session = Depends(get_db)):
    exists = _user_by_email(db, payload.email)
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=str(payload.email), password_hash=hash_password(payload.password))
    db.add(user); db.commit(); db.refresh(user)
    # issue tokens and persist refresh hash/jti
    access = create_access_token(user.id)
    refresh, jti = create_refresh_token(user.id)
    user.refresh_token_hash = pwd_context.hash(refresh)
    user.refresh_jti = jti
    db.add(user); db.commit()
    csrf = secrets.token_urlsafe(24)
    set_auth_cookies(response, access, refresh, csrf)
    return user

@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = _user_by_email(db, str(payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token(user.id)
    refresh, jti = create_refresh_token(user.id)
    user.refresh_token_hash = pwd_context.hash(refresh)
    user.refresh_jti = jti
    db.add(user); db.commit()
    csrf = secrets.token_urlsafe(24)
    set_auth_cookies(response, access, refresh, csrf)
    return user

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
    # verify token matches stored hash and jti (rotation)
    if payload.get("jti") != user.refresh_jti or not pwd_context.verify(token, user.refresh_token_hash):
        raise HTTPException(status_code=401, detail="Refresh revoked")
    # rotate
    access = create_access_token(user.id)
    refresh_new, jti_new = create_refresh_token(user.id)
    user.refresh_token_hash = pwd_context.hash(refresh_new)
    user.refresh_jti = jti_new
    db.add(user); db.commit()
    csrf = secrets.token_urlsafe(24)
    set_auth_cookies(response, access, refresh_new, csrf)
    return user

@router.post("/logout")
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    # optional: require CSRF for logout as well
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
        db.add(access_user); db.commit()
    return {"ok": True}

@router.get("/me", response_model=UserOut)
def me(request: Request, db: Session = Depends(get_db)):
    user = _verify_and_get_user_from_access(request, db)
    return user