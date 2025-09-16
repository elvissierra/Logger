"""
User model (Knowledge Drop)

What this file does
- Declares the SQLAlchemy model for users, including indexes for login and token management.

How it collaborates
- Auth routes create/verify users, rotate refresh tokens, and check token_version for invalidation.

Why necessary
- Central place to enforce uniqueness on email and store refresh token hashes/JTI for revocation.

Notes
- token_version lets you force-logout users by bumping the version; last_password_change aids forensics.
"""
from sqlalchemy import Column, String, Boolean, TIMESTAMP, Text, func, Index
import uuid
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    # Indexes: unique email for login; refresh_jti lookup for token rotation/invalidation.
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_refresh_jti", "refresh_jti"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Core credentials; password stored as a hash using passlib's bcrypt.
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    # Account status flags used by auth logic and admin screens.
    is_active = Column(Boolean, nullable=False, server_default="true")
    email_verified = Column(Boolean, nullable=False, server_default="false")
    # Security metadata used to invalidate tokens and track password changes.
    token_version = Column(String, nullable=False, server_default="0")
    last_password_change = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    # Store a hash of the refresh token and its JTI so you can revoke/rotate securely without storing raw tokens.
    refresh_token_hash = Column(Text, nullable=True)
    refresh_jti = Column(String, nullable=True)

    # Timestamps for audit trails and cache invalidation.
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)