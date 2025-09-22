from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routes.auth import _verify_and_get_user_from_access
from app.schemas.project import ProjectOut, ProjectUpdate, ProjectCreate
from app.crud.projects import list_projects as crud_list, get_by_code, update_project, upsert_by_code

router = APIRouter()

@router.get("/", response_model=List[ProjectOut])
def api_list_projects(db: Session = Depends(get_db), user=Depends(_verify_and_get_user_from_access)):
    return crud_list(db, user_id=user.id)

@router.patch("/{code}", response_model=ProjectOut)
def api_update_project(code: str, payload: ProjectUpdate, db: Session = Depends(get_db), user=Depends(_verify_and_get_user_from_access)):
    proj = get_by_code(db, user_id=user.id, code=code)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return update_project(db, proj, payload)

@router.post("/upsert", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def api_upsert_project(payload: ProjectCreate, db: Session = Depends(get_db), user=Depends(_verify_and_get_user_from_access)):
    return upsert_by_code(db, user_id=user.id, payload=payload)