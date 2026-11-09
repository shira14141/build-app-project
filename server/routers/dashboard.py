"""נתונים למסכי הסיכום: לוח בקרה הנהלה, ומשימות פתוחות למסך 'היום'.
הכל מחושב במסד, רק על הפרויקטים שהמשתמש רשאי לראות."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from constants import PERM_VIEW_DASHBOARD, STATUSES, STATUS_DONE
from server.auth import get_current_user, require_permission, visible_projects_query
from server.db import get_db
from server.models import Project, Task, User
from server.routers.projects import build_summaries, task_out
from server.schemas import DashboardOut, OpenTaskOut

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary", response_model=DashboardOut)
def dashboard_summary(user: User = Depends(require_permission(PERM_VIEW_DASHBOARD)), db: Session = Depends(get_db)):
    projects = visible_projects_query(db, user).order_by(Project.id).all()
    ids = [p.id for p in projects]
    status_counts = {s: 0 for s in STATUSES}
    open_by_assignee = {}
    if ids:
        for status, count in (db.query(Task.status, func.count()).filter(Task.project_id.in_(ids))
                              .group_by(Task.status)):
            status_counts[status] = count
        open_by_assignee = dict(db.query(Task.assigned_to, func.count())
                                .filter(Task.project_id.in_(ids), Task.status != STATUS_DONE)
                                .group_by(Task.assigned_to))
    return DashboardOut(projects=build_summaries(db, projects), status_counts=status_counts,
                        open_by_assignee=open_by_assignee)


@router.get("/tasks/open", response_model=list[OpenTaskOut])
def open_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """כל המשימות הפתוחות בפרויקטים שהמשתמש רואה, עם שם הפרויקט - בשאילתה אחת.
    המסך 'היום' מציג מהן את שלי, ולמנהלים גם את הדחופות של אחרים."""
    project_ids = visible_projects_query(db, user).with_entities(Project.id).subquery()
    rows = (db.query(Task, Project.name).join(Project, Task.project_id == Project.id)
            .filter(Task.project_id.in_(project_ids.select()), Task.status != STATUS_DONE)
            .order_by(Task.priority.desc(), Project.name))
    return [OpenTaskOut(**task_out(t), project_id=t.project_id, project_name=name) for t, name in rows]
