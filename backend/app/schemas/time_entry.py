

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TimeEntryBase(BaseModel):
    user_id: str
    project_code: str
    activity: str
    start_utc: datetime
    end_utc: datetime
    notes: Optional[str] = None


class TimeEntryCreate(TimeEntryBase):
    pass


class TimeEntryUpdate(BaseModel):
    project_code: Optional[str] = None
    activity: Optional[str] = None
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None
    notes: Optional[str] = None


class TimeEntryOut(BaseModel):
    id: str
    org_id: Optional[str] = None
    user_id: str
    project_code: str
    activity: str
    start_utc: datetime
    end_utc: datetime
    seconds: int
    notes: Optional[str] = None

    class Config:
        orm_mode = True