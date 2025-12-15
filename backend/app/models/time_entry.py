"""
TimeEntry model (Knowledge Drop)

What this file does
- Declares the SQLAlchemy model for time entries and an index for common queries (user_id, start_utc).

How it collaborates
- CRUD uses this model to persist and query entries; Pydantic schemas serialize ORM rows with from_attributes.

Why necessary
- Centralized schema definition; ensures DB constraints and query performance (index) for weekly views.

Notes
- end_utc is nullable to allow running entries; seconds is materialized on write for reporting speed.
"""

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    TIMESTAMP,
    func,
    Index,
)  # ⬅ add Index
import uuid

from app.core.database import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"
    # Composite index speeds up per-user time range scans used by weekly views.
    __table_args__ = (Index("ix_time_entries_user_start", "user_id", "start_utc"),)
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # org_id reserved for future multi-tenant/org support; user_id ties the entry to the owner (FK in future).
    org_id = Column(String, nullable=True)  # optional until orgs are added
    user_id = Column(String, nullable=False)  # later -> FK to users.id
    project_code = Column(String, nullable=False)
    # activity kept as a simple label for now; can evolve to a normalized table later.
    activity = Column(String, nullable=False)
    job_title = Column(String, nullable=True)
    start_utc = Column(TIMESTAMP(timezone=True), nullable=False)
    # allow running entries to have no end yet; API computes/stores seconds when ended
    end_utc = Column(TIMESTAMP(timezone=True), nullable=True)
    # Denormalized duration (seconds) stored to simplify reporting without recomputing at query time.
    seconds = Column(Integer, nullable=False)  # computed in CRUD on create/update

    notes = Column(Text, nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    # updated_at auto-bumps on changes for audit and cache invalidation.
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Derived flag used by API serializers and clients to show a live "running" state when end_utc is null.
    @property
    def running(self) -> bool:
        """True when the entry has a start but no end time yet."""
        try:
            return bool(self.start_utc) and (self.end_utc is None)
        except Exception:
            return False
