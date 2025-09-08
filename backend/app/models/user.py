from sqlalchemy import Column, String, Boolean, TIMESTAMP, Text, func, Index
import uuid
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_refresh_jti", "refresh_jti"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    # store the *hash* of the latest refresh token (rotate on each refresh/login)
    refresh_token_hash = Column(Text, nullable=True)
    refresh_jti = Column(String, nullable=True)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)