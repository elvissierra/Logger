"""
Organization model (Knowledge Drop)

What this file does
- Declares the SQLAlchemy model for organizations, including indexes for invite code lookups.

How it collaborates
- Auth routes will validate org memberships and admins against this table.
- Users have a foreign key reference to organizations for multi-tenant isolation.

Why necessary
- Central place to store organization data and enforce uniqueness on invite codes.

Notes
- invite_code is unique and indexed for fast lookups during org joins.
- headcount is a simple integer to track org size.
"""

from sqlalchemy import Column, String, Integer, TIMESTAMP, func, Index
import uuid
from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"
    # Indexes: unique invite code for org invitations/joins.
    __table_args__ = (
        Index("ix_organizations_invite_code", "invite_code", unique=True),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    headcount = Column(Integer, nullable=False)
    invite_code = Column(String, unique=True, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
