"""היומן האישי. כל משתמש רואה ומשנה רק את המשימות שלו - המשתמש נלקח מהטוקן, לא מהכתובת."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.auth import get_current_user
from server.db import get_db
from server.models import PersonalTask, User
from server.schemas import PersonalStatusUpdate, PersonalTaskCreate, PersonalTaskOut

router = APIRouter(prefix="/personal_tasks", tags=["personal tasks"])


def _own_task(db: Session, user: User, task_id: str) -> PersonalTask:
    task = db.query(PersonalTask).filter_by(id=task_id, assigned_to=user.username).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/", response_model=list[PersonalTaskOut])
def list_my_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [PersonalTaskOut(id=t.id, title=t.title, assigned_to=t.assigned_to, priority=t.priority,
                            status=t.status, date=t.date or "")
            for t in db.query(PersonalTask).filter_by(assigned_to=user.username)]


@router.post("/", status_code=201)
def add_my_task(req: PersonalTaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = PersonalTask(id=str(uuid.uuid4()), title=req.title, assigned_to=user.username, priority=req.priority,
                        date=req.date.isoformat())
    db.add(task)
    db.commit()
    return {"id": task.id}


@router.patch("/{task_id}")
def update_my_task_status(task_id: str, req: PersonalStatusUpdate, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    task = _own_task(db, user, task_id)
    task.status = req.status
    db.commit()
    return {"status": task.status}


@router.delete("/{task_id}", status_code=204)
def delete_my_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_own_task(db, user, task_id))
    db.commit()
