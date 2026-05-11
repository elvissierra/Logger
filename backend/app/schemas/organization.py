"""
Knowledge Drop — app/schemas/organization.py (Organization schemas)

What this file does
- Declares request/response schemas for organization endpoints.

How it works with other resources
- routes/organizations.py uses these models to validate payloads and shape responses.

Why it's necessary
- Keeps the external contract explicit and documented in OpenAPI.

Notes
- `OrgOut` includes invite_code for membership setup flows.
- `MemberOut` represents a user within an organization context.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OrgCreate(BaseModel):
    name: str
    address: str
    phone: str
    headcount: int


class OrgUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    headcount: int | None = None


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    address: str
    phone: str
    headcount: int
    invite_code: str


class OrgCodeCheck(BaseModel):
    org_name: str


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    account_type: str
    is_org_admin: bool
    created_at: datetime
