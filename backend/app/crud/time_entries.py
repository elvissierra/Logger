"""
Time entry CRUD (Knowledge Drop)

What this file does
- Implements listing, creation, update, delete, overlap detection, and duration computation for time entries.

How it collaborates
- Models: app.models.time_entry.TimeEntry
- Schemas: app.schemas.time_entry.TimeEntryCreate/Update used by routes
- Routes call these helpers with a Session from get_db().

Why necessary
- Keeps data rules (seconds recompute, overlap constraints) in one place so both API and background jobs are consistent.
"""

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
    """
    List entries with optional filters.
    - Filters by user when user_id is provided.
    - If both date_from and date_to are provided, returns entries with start_utc in [date_from, date_to).
    - Orders newest-first to support UIs that show recent work on top.
    """
    # Base query; subsequent filters are composed conditionally.
    q = db.query(TimeEntry)
    if user_id:
        q = q.filter(TimeEntry.user_id == user_id)
    if date_from and date_to:
        q = q.filter(
            and_(TimeEntry.start_utc >= date_from, TimeEntry.start_utc < date_to)
        )
    elif date_from:
        q = q.filter(TimeEntry.start_utc >= date_from)
    elif date_to:
        q = q.filter(TimeEntry.start_utc < date_to)
    # Keep the query bounded; large ranges should be paginated (skip/limit).
    return q.order_by(TimeEntry.start_utc.desc()).offset(skip).limit(limit).all()


def get_entry(db: Session, entry_id: str) -> Optional[TimeEntry]:
    return db.get(TimeEntry, entry_id)


def _compute_seconds(start_utc: datetime, end_utc: datetime) -> int:
    """Pure function for duration; guards against negative intervals (clock skew / bad input)."""
    return max(0, int((end_utc - start_utc).total_seconds()))


def has_overlap(
    db: Session,
    *,
    user_id: str,
    start_utc: datetime,
    end_utc: datetime,
    exclude_id: Optional[str] = None,
) -> bool:
    """
    True if another entry for the same user overlaps the given interval.
    Overlap test: existing.end > start AND existing.start < end (half-open interval semantics).
    Used to prevent double-booking when creating or updating entries.
    """
    q = db.query(TimeEntry).filter(TimeEntry.user_id == user_id)
    q = q.filter(TimeEntry.end_utc > start_utc, TimeEntry.start_utc < end_utc)
    if exclude_id:
        q = q.filter(TimeEntry.id != exclude_id)
    return db.query(q.exists()).scalar()  # type: ignore[arg-type]


def create_entry(db: Session, payload: TimeEntryCreate) -> TimeEntry:
    """Create entry and materialize seconds at write time so reports can use the column without recompute."""
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
    """Patch entry fields and recompute seconds when start/end change; persists and refreshes in one transaction."""
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
