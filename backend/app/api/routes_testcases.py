from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import verify_admin_key
from app.db.models import Project, Testcase
from app.db.session import get_db
from app.evals.testcases import load_default_testcases

router = APIRouter(dependencies=[Depends(verify_admin_key)])


@router.post("/projects/{project_id}/seed-testcases")
def seed_testcases(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    count = load_default_testcases(db, project.id)
    return {"inserted": count}


@router.get("/projects/{project_id}/testcases")
def list_testcases(project_id: str, db: Session = Depends(get_db)):
    rows = db.query(Testcase).filter(Testcase.project_id == project_id).all()
    return [
        {
            "id": str(row.id),
            "type": row.type,
            "name": row.name,
            "prompt": row.prompt,
            "expected_behavior": row.expected_behavior,
            "severity": row.severity,
            "tags": row.tags,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
