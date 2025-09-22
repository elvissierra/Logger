"""
Project model (minimal)
- Per-user project catalog with creation timestamp and optional metadata.
"""
from sqlalchemy import Column, String, TIMESTAMP, Text, func, Index
import uuid
from app.core.database import Base

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_user_code", "user_id", "code", unique=True),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)      # later can be FK to users.id
    code = Column(String, nullable=False)         # e.g., "PJ-001" (unique per user)
    name = Column(String, nullable=True)          # optional display name
    description = Column(Text, nullable=True)     # optional
    priority = Column(String, nullable=True)      # Low/Normal/High/Critical (optional)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)