

from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.time_entry import TimeEntry
from app.schemas.time_entry import TimeEntryCreate, TimeEntryUpdate


def list_entries(db: Session, skip: int = 0, limit: int = 100) -> List[TimeEntry]:
    return (
        db.query(TimeEntry)
        .order_by(TimeEntry.start_utc.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_entry(db: Session, entry_id: str) -> Optional[TimeEntry]:
    return db.query(TimeEntry).get(entry_id)


def _compute_seconds(start_utc: datetime, end_utc: datetime) -> int:
    return max(0, int((end_utc - start_utc).total_seconds()))


def create_entry(db: Session, payload: TimeEntryCreate) -> TimeEntry:
    seconds = _compute_seconds(payload.start_utc, payload.end_utc)
    obj = TimeEntry(
        org_id=None,
        user_id=payload.user_id,
        project_code=payload.project_code,
        activity=payload.activity,
        start_utc=payload.start_utc,
        end_utc=payload.end_utc,
        seconds=seconds,
        notes=payload.notes,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_entry(db: Session, entry: TimeEntry, payload: TimeEntryUpdate) -> TimeEntry:
    data = payload.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(entry, k, v)
    # recompute seconds if times were touched
    if "start_utc" in data or "end_utc" in data:
        entry.seconds = _compute_seconds(entry.start_utc, entry.end_utc)
    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: Session, entry: TimeEntry) -> None:
    db.delete(entry)
    db.commit()