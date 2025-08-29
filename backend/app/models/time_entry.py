

from sqlalchemy import Column, String, Text, Integer, TIMESTAMP, func
import uuid

from app.core.database import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String, nullable=True)       # optional until orgs are added
    user_id = Column(String, nullable=False)     # later -> FK to users.id
    project_code = Column(String, nullable=False)
    activity = Column(String, nullable=False)

    start_utc = Column(TIMESTAMP(timezone=True), nullable=False)
    end_utc = Column(TIMESTAMP(timezone=True), nullable=False)
    seconds = Column(Integer, nullable=False)    # computed in CRUD on create/update

    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)