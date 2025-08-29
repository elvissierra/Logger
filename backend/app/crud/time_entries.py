from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime

from app.models.time_entry import TimeEntry
from app.schemas.time_entry import TimeEntryCreate, TimeEntryUpdate


def list_entries(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[TimeEntry]:
    """List entries with optional filters.
    If both date_from and date_to are provided, filter by start_utc in [date_from, date_to).
    """
    q = db.query(TimeEntry)
    if user_id:
        q = q.filter(TimeEntry.user_id == user_id)
    if date_from and date_to:
        q = q.filter(and_(TimeEntry.start_utc >= date_from, TimeEntry.start_utc < date_to))
    elif date_from:
        q = q.filter(TimeEntry.start_utc >= date_from)
    elif date_to:
        q = q.filter(TimeEntry.start_utc < date_to)
    return (
        q.order_by(TimeEntry.start_utc.desc())
         .offset(skip)
         .limit(limit)
         .all()
    )


def get_entry(db: Session, entry_id: str) -> Optional[TimeEntry]:
    return db.get(TimeEntry, entry_id)


def _compute_seconds(start_utc: datetime, end_utc: datetime) -> int:
    return max(0, int((end_utc - start_utc).total_seconds()))


def has_overlap(
    db: Session,
    *,
    user_id: str,
    start_utc: datetime,
    end_utc: datetime,
    exclude_id: Optional[str] = None,
) -> bool:
    """True if another entry for the same user overlaps the given interval.
    Overlap test: existing.end > start AND existing.start < end
    """
    q = db.query(TimeEntry).filter(TimeEntry.user_id == user_id)
    q = q.filter(TimeEntry.end_utc > start_utc, TimeEntry.start_utc < end_utc)
    if exclude_id:
        q = q.filter(TimeEntry.id != exclude_id)
    return db.query(q.exists()).scalar()  # type: ignore[arg-type]


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