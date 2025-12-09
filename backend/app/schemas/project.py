from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional


class ProjectBase(BaseModel):
    code: str
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None


class ProjectOut(ProjectBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
