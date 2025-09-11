from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from app.routes.auth import _verify_and_get_user_from_access
from app.core.database import get_db
from app.core.security import require_csrf
from sqlalchemy.orm import Session

# Use shared schemas to avoid duplication
from app.schemas.time_entry import TimeEntryCreate, TimeEntryUpdate, TimeEntryOut

# Use shared CRUD helpers
from app.crud.time_entries import (
    list_entries as crud_list_entries,
    create_entry as crud_create_entry,
    get_entry as crud_get_entry,
    update_entry as crud_update_entry,
    delete_entry as crud_delete_entry,
    has_overlap as crud_has_overlap,
)

router = APIRouter()

# -----------------
# API Routes
# -----------------
@router.get("/", response_model=List[TimeEntryOut])
def api_list_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    date_from: Optional[datetime] = Query(None, alias="from", description="UTC ISO start inclusive"),
    date_to: Optional[datetime] = Query(None, alias="to", description="UTC ISO end exclusive"),
    db: Session = Depends(get_db),
    user=Depends(_verify_and_get_user_from_access),
):
    # Always scope to the authenticated user for privacy
    return crud_list_entries(db, skip=skip, limit=limit, user_id=user.id, date_from=date_from, date_to=date_to)

@router.post("/", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
def api_create_entry(payload: TimeEntryCreate, request: Request, db: Session = Depends(get_db), user=Depends(_verify_and_get_user_from_access)):
    require_csrf(request)
    if payload.end_utc <= payload.start_utc:
        raise HTTPException(status_code=400, detail="end_utc must be greater than start_utc")
    if crud_has_overlap(db, user_id=user.id, start_utc=payload.start_utc, end_utc=payload.end_utc):
        raise HTTPException(status_code=409, detail="Overlapping time entry for user")
    # Force server-side ownership to the authenticated user
    payload2 = TimeEntryCreate(**{**payload.dict(), "user_id": user.id})
    return crud_create_entry(db, payload2)

@router.get("/{entry_id}", response_model=TimeEntryOut)
def api_get_entry(entry_id: str, db: Session = Depends(get_db), user=Depends(_verify_and_get_user_from_access)):
    entry = crud_get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")
    if entry.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return entry

@router.patch("/{entry_id}", response_model=TimeEntryOut)
def api_update_entry(entry_id: str, payload: TimeEntryUpdate, request: Request, db: Session = Depends(get_db), user=Depends(_verify_and_get_user_from_access)):
    entry = crud_get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")
    require_csrf(request)
    if entry.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    # Derive final times for validation
    new_start = payload.start_utc or entry.start_utc
    new_end = payload.end_utc or entry.end_utc
    if new_end <= new_start:
        raise HTTPException(status_code=400, detail="end_utc must be greater than start_utc")
    if crud_has_overlap(db, user_id=entry.user_id, start_utc=new_start, end_utc=new_end, exclude_id=entry.id):
        raise HTTPException(status_code=409, detail="Overlapping time entry for user")
    return crud_update_entry(db, entry, payload)

@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_entry(entry_id: str, request: Request, db: Session = Depends(get_db), user=Depends(_verify_and_get_user_from_access)):
    entry = crud_get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")
    require_csrf(request)
    if entry.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    crud_delete_entry(db, entry)
    return None