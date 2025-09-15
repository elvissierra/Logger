from sqlalchemy import Column, String, Text, Integer, TIMESTAMP, func, Index  # ⬅ add Index
import uuid

from app.core.database import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (Index("ix_time_entries_user_start", "user_id", "start_utc"),)
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String, nullable=True)       # optional until orgs are added
    user_id = Column(String, nullable=False)     # later -> FK to users.id
    project_code = Column(String, nullable=False)
    activity = Column(String, nullable=False)

    start_utc = Column(TIMESTAMP(timezone=True), nullable=False)
    # allow running entries to have no end yet; API computes/stores seconds when ended
    end_utc   = Column(TIMESTAMP(timezone=True), nullable=True)
    seconds   = Column(Integer, nullable=False)  # computed in CRUD on create/update

    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Computed flags/metrics for API serializers (Pydantic from_attributes)
    @property
    def running(self) -> bool:
        """True when the entry has a start but no end time yet."""
        try:
            return bool(self.start_utc) and (self.end_utc is None)
        except Exception:
            return False
