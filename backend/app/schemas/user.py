"""
Knowledge Drop — app/schemas/user.py (Auth schemas)

What this file does
- Declares request/response schemas for auth endpoints.

How it works with other resources
- routes/auth.py uses these models to validate payloads and shape responses.

Why it’s necessary
- Keeps the external contract explicit and documented in OpenAPI.

Notes
- `UserOut` intentionally omits sensitive fields like password_hash and refresh state.
"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, Field


# Payload for /register; server handles email uniqueness and password hashing
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


# Payload for /login
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Public-facing user profile; from_attributes=True allows passing ORM instances directly
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime
