"""
Knowledge Drop — app/crud/organizations.py (Organization CRUD operations)

What this file does
- Implements database operations for organizations and membership.

How it works with other resources
- routes/organizations.py calls these functions to create, read, update, and delete organizations.
- Uses SQLAlchemy 2.0 Session for all database access.

Why it's necessary
- Separates data access from route handlers, enabling testability and code reuse.

Notes
- `create_org()` generates a unique invite code and sets the creator as org admin.
- `get_org_members()` retrieves all users in an organization.
- `update_org()` uses `model_dump(exclude_none=True)` to apply only provided fields.
"""

import secrets
from sqlalchemy.orm import Session
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrgCreate, OrgUpdate


def _generate_invite_code() -> str:
    """Generate a URL-safe random invite code."""
    return secrets.token_urlsafe(8)


def create_org(db: Session, payload: OrgCreate, creator: User) -> Organization:
    """
    Create a new organization and set the creator as its admin.

    Args:
        db: Database session
        payload: OrgCreate schema with organization details
        creator: User object of the organization creator

    Returns:
        Newly created Organization instance
    """
    code = _generate_invite_code()
    while db.query(Organization).filter(Organization.invite_code == code).first():
        code = _generate_invite_code()

    org = Organization(
        name=payload.name,
        address=payload.address,
        phone=payload.phone,
        headcount=payload.headcount,
        invite_code=code,
    )
    db.add(org)
    db.flush()  # get org.id before updating user

    creator.org_id = org.id
    creator.is_org_admin = True
    creator.account_type = "org_member"
    db.commit()
    db.refresh(org)
    db.refresh(creator)
    return org


def get_org_by_invite_code(db: Session, code: str) -> Organization | None:
    """
    Retrieve an organization by its invite code.

    Args:
        db: Database session
        code: Invite code to look up

    Returns:
        Organization instance or None if not found
    """
    return db.query(Organization).filter(Organization.invite_code == code).first()


def get_org_by_id(db: Session, org_id: str) -> Organization | None:
    """
    Retrieve an organization by its ID.

    Args:
        db: Database session
        org_id: Organization ID to look up

    Returns:
        Organization instance or None if not found
    """
    return db.query(Organization).filter(Organization.id == org_id).first()


def get_org_members(db: Session, org_id: str) -> list[User]:
    """
    Retrieve all members of an organization.

    Args:
        db: Database session
        org_id: Organization ID

    Returns:
        List of User instances in the organization
    """
    return db.query(User).filter(User.org_id == org_id).all()


def update_org(db: Session, org: Organization, payload: OrgUpdate) -> Organization:
    """
    Update an organization with new values.

    Args:
        db: Database session
        org: Organization instance to update
        payload: OrgUpdate schema with fields to update

    Returns:
        Updated Organization instance
    """
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(org, field, value)
    db.commit()
    db.refresh(org)
    return org
