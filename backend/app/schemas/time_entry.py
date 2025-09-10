from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class TimeEntryBase(BaseModel):
    project_code: str
    activity: str
    start_utc: datetime
    end_utc: datetime
    notes: Optional[str] = None

class TimeEntryCreate(TimeEntryBase):
    user_id: Optional[str] = None

class TimeEntryUpdate(BaseModel):
    project_code: Optional[str] = None
    activity: Optional[str] = None
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None
    notes: Optional[str] = None

class TimeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: Optional[str] = None
    user_id: str
    project_code: str
    activity: str
    running: bool
    start_utc: datetime
    end_utc: datetime
    seconds: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime