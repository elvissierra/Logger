from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.time_entry import TimeEntry

router = APIRouter()

# -----------------
# Pydantic Schemas
# -----------------
class TimeEntryBase(BaseModel):
    project_code: str
    activity: str
    start_utc: datetime
    end_utc: datetime
    notes: Optional[str] = None

class TimeEntryCreate(TimeEntryBase):
    user_id: str

class TimeEntryUpdate(BaseModel):
    project_code: Optional[str] = None
    activity: Optional[str] = None
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None
    notes: Optional[str] = None

class TimeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    project_code: str
    activity: str
    start_utc: datetime
    end_utc: datetime
    seconds: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

# -----------------
# Helpers / CRUD
# -----------------
def _duration_seconds(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds()))

def has_overlap(
    db: Session, *, user_id: str, start_utc: datetime, end_utc: datetime, exclude_id: Optional[str] = None
) -> bool:
    """True if any entry for user overlaps [start_utc, end_utc)."""
    q = db.query(TimeEntry).filter(TimeEntry.user_id == user_id)
    if exclude_id:
        q = q.filter(TimeEntry.id != exclude_id)
    # overlap if (existing.end > start) AND (existing.start < end)
    q = q.filter(and_(TimeEntry.end_utc > start_utc, TimeEntry.start_utc < end_utc))
    return db.query(q.exists()).scalar()

def list_entries(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[TimeEntry]:
    q = db.query(TimeEntry)
    if user_id:
        q = q.filter(TimeEntry.user_id == user_id)
    if date_from and date_to:
        q = q.filter(and_(TimeEntry.end_utc > date_from, TimeEntry.start_utc < date_to))
    elif date_from:
        q = q.filter(TimeEntry.end_utc > date_from)
    elif date_to:
        q = q.filter(TimeEntry.start_utc < date_to)
    q = q.order_by(TimeEntry.start_utc.asc()).offset(skip).limit(limit)
    return q.all()

def create_entry(db: Session, payload: TimeEntryCreate) -> TimeEntry:
    seconds = _duration_seconds(payload.start_utc, payload.end_utc)
    obj = TimeEntry(
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

def get_entry(db: Session, entry_id: str) -> Optional[TimeEntry]:
    return db.get(TimeEntry, entry_id)

def update_entry(db: Session, entry: TimeEntry, payload: TimeEntryUpdate) -> TimeEntry:
    # apply updates
    if payload.project_code is not None:
        entry.project_code = payload.project_code
    if payload.activity is not None:
        entry.activity = payload.activity
    if payload.start_utc is not None:
        entry.start_utc = payload.start_utc
    if payload.end_utc is not None:
        entry.end_utc = payload.end_utc
    if payload.notes is not None:
        entry.notes = payload.notes

    entry.seconds = _duration_seconds(entry.start_utc, entry.end_utc)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

def delete_entry(db: Session, entry: TimeEntry) -> None:
    db.delete(entry)
    db.commit()

# -----------------
# API Routes
# -----------------
@router.get("/", response_model=List[TimeEntryOut])
def api_list_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    date_from: Optional[datetime] = Query(None, alias="from", description="UTC ISO start inclusive"),
    date_to: Optional[datetime] = Query(None, alias="to", description="UTC ISO end exclusive"),
    db: Session = Depends(get_db),
):
    return list_entries(db, skip=skip, limit=limit, user_id=user_id, date_from=date_from, date_to=date_to)

@router.post("/", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
def api_create_entry(payload: TimeEntryCreate, db: Session = Depends(get_db)):
    if payload.end_utc <= payload.start_utc:
        raise HTTPException(status_code=400, detail="end_utc must be greater than start_utc")
    if has_overlap(db, user_id=payload.user_id, start_utc=payload.start_utc, end_utc=payload.end_utc):
        raise HTTPException(status_code=409, detail="Overlapping time entry for user")
    return create_entry(db, payload)

@router.get("/{entry_id}", response_model=TimeEntryOut)
def api_get_entry(entry_id: str, db: Session = Depends(get_db)):
    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")
    return entry

@router.patch("/{entry_id}", response_model=TimeEntryOut)
def api_update_entry(entry_id: str, payload: TimeEntryUpdate, db: Session = Depends(get_db)):
    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")

    # Derive final times for validation
    new_start = payload.start_utc or entry.start_utc
    new_end = payload.end_utc or entry.end_utc
    if new_end <= new_start:
        raise HTTPException(status_code=400, detail="end_utc must be greater than start_utc")
    if has_overlap(db, user_id=entry.user_id, start_utc=new_start, end_utc=new_end, exclude_id=entry.id):
        raise HTTPException(status_code=409, detail="Overlapping time entry for user")

    return update_entry(db, entry, payload)

@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_entry(entry_id: str, db: Session = Depends(get_db)):
    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")
    delete_entry(db, entry)
    return None