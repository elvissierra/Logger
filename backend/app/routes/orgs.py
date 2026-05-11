from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.crud import organizations as org_crud
from app.schemas.organization import OrgCreate, OrgOut, OrgUpdate, OrgCodeCheck, MemberOut
from app.routes.auth import _verify_and_get_user_from_access
from starlette.requests import Request

router = APIRouter()


def _require_org_admin(user):
    if not user.is_org_admin:
        raise HTTPException(status_code=403, detail="Org admin access required")


@router.get("/validate-code", response_model=OrgCodeCheck)
def validate_invite_code(code: str, db: Session = Depends(get_db)):
    org = org_crud.get_org_by_invite_code(db, code)
    if not org:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    return OrgCodeCheck(org_name=org.name)


@router.post("/", response_model=OrgOut, status_code=201)
def create_org(
    payload: OrgCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _verify_and_get_user_from_access(request, db)
    if user.org_id:
        raise HTTPException(status_code=400, detail="User already belongs to an organization")
    org = org_crud.create_org(db, payload, user)
    return org


@router.get("/me", response_model=OrgOut)
def get_my_org(request: Request, db: Session = Depends(get_db)):
    user = _verify_and_get_user_from_access(request, db)
    if not user.org_id:
        raise HTTPException(status_code=404, detail="User has no organization")
    org = org_crud.get_org_by_id(db, user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("/members", response_model=list[MemberOut])
def get_org_members(request: Request, db: Session = Depends(get_db)):
    user = _verify_and_get_user_from_access(request, db)
    _require_org_admin(user)
    return org_crud.get_org_members(db, user.org_id)


@router.patch("/", response_model=OrgOut)
def update_org(
    payload: OrgUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _verify_and_get_user_from_access(request, db)
    _require_org_admin(user)
    org = org_crud.get_org_by_id(db, user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org_crud.update_org(db, org, payload)
