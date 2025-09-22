from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate

def get_by_code(db: Session, user_id: str, code: str) -> Optional[Project]:
    return db.query(Project).filter(Project.user_id == user_id, Project.code == code).first()

def upsert_by_code(db: Session, user_id: str, payload: ProjectCreate) -> Project:
    proj = get_by_code(db, user_id, payload.code)
    if proj:
        changed = False
        for k in ("name", "description", "priority"):
            v = getattr(payload, k, None)
            if v is not None and getattr(proj, k) != v:
                setattr(proj, k, v); changed = True
        if changed:
            db.add(proj); db.commit(); db.refresh(proj)
        return proj
    proj = Project(user_id=user_id, code=payload.code, name=payload.name, description=payload.description, priority=payload.priority)
    db.add(proj); db.commit(); db.refresh(proj)
    return proj

def list_projects(db: Session, user_id: str) -> List[Project]:
    return db.query(Project).filter(Project.user_id == user_id).order_by(Project.created_at.asc()).all()

def update_project(db: Session, proj: Project, payload: ProjectUpdate) -> Project:
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(proj, k, v)
    db.add(proj); db.commit(); db.refresh(proj)
    return proj