"""
Knowledge Drop — app/schemas/time_entry.py (Pydantic models for API)

What this file does
- Declares request/response schemas for time entry endpoints (Pydantic v2).

How it works with other resources
- Routes use these models for validation and OpenAPI docs; CRUD returns ORM models that are serialized via from_attributes.

Why it’s necessary
- Separates wire format (what the API exposes) from DB models, allowing internal changes without breaking clients.

Notes
- `TimeEntryOut.running` defaults to False so missing properties don’t break responses.
- `end_utc` is optional to allow running entries.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

# Common fields shared by create/update; persisted timestamps are UTC
class TimeEntryBase(BaseModel):
    project_code: str
    activity: str
    start_utc: datetime
    end_utc: Optional[datetime] = None
    notes: Optional[str] = None

# Server sets user_id from auth; field remains optional to accept client payloads
class TimeEntryCreate(TimeEntryBase):
    user_id: Optional[str] = None

# PATCH semantics: only provided fields are updated
class TimeEntryUpdate(BaseModel):
    project_code: Optional[str] = None
    activity: Optional[str] = None
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None
    notes: Optional[str] = None

# Response model including server-managed fields; from_attributes=True lets Pydantic read SQLAlchemy objects
class TimeEntryOut(BaseModel):
    id: str
    org_id: Optional[str] = None
    user_id: str
    project_code: str
    activity: str | None = None
    start_utc: datetime
    end_utc: Optional[datetime] = None
    seconds: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    running: bool = False

    model_config = ConfigDict(from_attributes=True)