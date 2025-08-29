from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.time_entry import TimeEntryCreate, TimeEntryUpdate, TimeEntryOut
from app.crud.time_entries import (
    list_entries,
    create_entry,
    get_entry,
    update_entry,
    delete_entry,
    has_overlap,
)

router = APIRouter()


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