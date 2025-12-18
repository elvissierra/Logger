"""
Knowledge Drop — app/routes/time_entries.py (Time Entry API)

What this file does
- FastAPI router exposing CRUD endpoints for time entries, with per-user scoping and CSRF protection.

How it works with other resources
- Depends on routes.auth._verify_and_get_user_from_access for authentication via access token cookie.
- Uses app.core.security.require_csrf for state-changing requests.
- Delegates persistence and business rules to app.crud.time_entries.

Why it’s necessary
- Keeps HTTP concerns (validation/status codes) separate from DB logic, and enforces multi-tenant isolation.

Notes
- The list endpoint always scopes to the authenticated user for privacy.
- Overlap checks prevent accidental double-tracking.
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from app.routes.auth import _verify_and_get_user_from_access
from app.core.database import get_db
from app.core.security import require_csrf
from sqlalchemy.orm import Session

import logging

log = logging.getLogger("uvicorn.error")

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
    get_running_entry as crud_get_running_entry,
)
from app.crud.projects import upsert_by_code
from app.schemas.project import ProjectCreate

router = APIRouter()  # Router is mounted under /api/time-entries in main.py


# GET / — list entries for current user with optional date window
@router.get("/", response_model=List[TimeEntryOut])
def api_list_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    date_from: Optional[datetime] = Query(
        None, alias="from", description="UTC ISO start inclusive"
    ),
    date_to: Optional[datetime] = Query(
        None, alias="to", description="UTC ISO end exclusive"
    ),
    db: Session = Depends(get_db),
    user=Depends(_verify_and_get_user_from_access),
):
    # Always scope to the authenticated user for privacy
    return crud_list_entries(
        db,
        skip=skip,
        limit=limit,
        user_id=user.id,
        date_from=date_from,
        date_to=date_to,
    )


# POST / — create entry (CSRF protected); ownership forced to current user
@router.post("/", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
def api_create_entry(
    payload: TimeEntryCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(_verify_and_get_user_from_access),
):
    require_csrf(request)

    # Force server-side ownership to the authenticated user
    payload2 = TimeEntryCreate(**{**payload.model_dump(), "user_id": user.id})

    # Validation: only enforce end > start when an end is provided (stopped entries)
    if payload2.end_utc is not None and payload2.end_utc <= payload2.start_utc:
        raise HTTPException(status_code=400, detail="end_utc must be greater than start_utc")

    # Rule A3: only one running entry per user at a time
    if payload2.end_utc is None:
        running = crud_get_running_entry(db, user_id=user.id)
        if running is not None:
            raise HTTPException(status_code=409, detail="A timer is already running")

    # Overlap checks only apply to closed intervals
    if payload2.end_utc is not None:
        if crud_has_overlap(db, user_id=user.id, start_utc=payload2.start_utc, end_utc=payload2.end_utc):
            raise HTTPException(status_code=409, detail="Overlapping time entry for user")

    # Ensure project exists for this user (best-effort).
    # If upsert fails, rollback the session; otherwise subsequent DB work in this request can fail
    # with InFailedSqlTransaction.
    try:
        upsert_by_code(db, user_id=user.id, payload=ProjectCreate(code=payload2.project_code))
    except Exception as e:
        db.rollback()
        log.warning(
            f"[projects] upsert_by_code failed (create_entry) user_id={user.id} code={payload2.project_code}: {e}"
        )

    return crud_create_entry(db, payload2)


# GET /{id} — fetch one; 404/403 enforced
@router.get("/{entry_id}", response_model=TimeEntryOut)
def api_get_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    user=Depends(_verify_and_get_user_from_access),
):
    entry = crud_get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")
    if entry.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return entry


# PATCH /{id} — partial update with overlap validation and CSRF
@router.patch("/{entry_id}", response_model=TimeEntryOut)
def api_update_entry(
    entry_id: str,
    payload: TimeEntryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(_verify_and_get_user_from_access),
):
    entry = crud_get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")
    require_csrf(request)
    if entry.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Merge PATCH semantics correctly (unset vs explicit null)
    data = payload.model_dump(exclude_unset=True)
    new_start = data.get("start_utc", entry.start_utc)
    # If the client provided end_utc explicitly (even if null), respect it; otherwise keep existing.
    new_end = data.get("end_utc", entry.end_utc)

    # Validate only when end exists
    if new_end is not None and new_end <= new_start:
        raise HTTPException(status_code=400, detail="end_utc must be greater than start_utc")

    # If patch would make this entry running, enforce "one running entry" rule
    if new_end is None:
        running = crud_get_running_entry(db, user_id=entry.user_id, exclude_id=entry.id)
        if running is not None:
            raise HTTPException(status_code=409, detail="A timer is already running")

    # Overlap check only for closed intervals
    if new_end is not None:
        if crud_has_overlap(
            db,
            user_id=entry.user_id,
            start_utc=new_start,
            end_utc=new_end,
            exclude_id=entry.id,
        ):
            raise HTTPException(status_code=409, detail="Overlapping time entry for user")

    try:
        if payload.project_code:
            upsert_by_code(
                db,
                user_id=entry.user_id,
                payload=ProjectCreate(code=payload.project_code),
            )
    except Exception as e:
        db.rollback()
        log.warning(
            f"[projects] upsert_by_code failed (update_entry) user_id={entry.user_id} code={payload.project_code}: {e}"
        )
    return crud_update_entry(db, entry, payload)


# DELETE /{id} — remove entry; CSRF and ownership enforced
@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_entry(
    entry_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(_verify_and_get_user_from_access),
):
    entry = crud_get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="TimeEntry not found")
    require_csrf(request)
    if entry.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    crud_delete_entry(db, entry)
    return None
