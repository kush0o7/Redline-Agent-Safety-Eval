from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import verify_admin_key
from app.db.models import Project
from app.db.session import get_db

router = APIRouter(dependencies=[Depends(verify_admin_key)])


class ProjectCreate(BaseModel):
    name: str


@router.post("/projects")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name)
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project name already exists")
    db.refresh(project)
    return {"id": str(project.id), "name": project.name, "created_at": project.created_at.isoformat()}
