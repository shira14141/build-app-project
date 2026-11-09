"""פרויקטים, משימות והוצאות. כל נתיב בודק שהמשתמש שותף בפרויקט ושיש לו את ההרשאה המתאימה."""
import datetime as dt
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from constants import (DEKEL_CATALOG, PERM_CREATE_PROJECT, PERM_DELETE_PROJECT, PERM_EDIT_PROJECT,
                       PERM_MANAGE_BUDGET, PERM_MANAGE_TASKS, PERM_UPDATE_OWN_TASKS, STATUS_BLOCKED, STATUS_DONE,
                       has_permission)
from server import storage
from server.auth import (can_see_all, create_file_token, get_current_user, get_project_for, require, require_permission,
                         visible_projects_query)
from server.db import get_db
from server.logging_setup import audit
from server.models import Expense, File, Project, ProjectMember, Task, User
from server.schemas import (ExpenseCreate, ProjectCreate, ProjectDetail, ProjectSummary, ProjectUpdate,
                            StatusUpdate, TaskBulkUpdate, TaskCreate)

router = APIRouter(tags=["projects"])


# =========================================================
# סיכומים - מחושבים במסד בכמה שאילתות קבועות, בלי קשר למספר הפרויקטים
# =========================================================
def build_summaries(db: Session, projects: list[Project]) -> list[ProjectSummary]:
    ids = [p.id for p in projects]
    if not ids:
        return []
    spent = dict(db.query(Expense.project_id, func.sum(Expense.final_price))
                 .filter(Expense.project_id.in_(ids)).group_by(Expense.project_id))
    files = dict(db.query(File.project_id, func.count()).filter(File.project_id.in_(ids)).group_by(File.project_id))
    tasks, done, blocked = defaultdict(int), defaultdict(int), defaultdict(int)
    for pid, status, count in (db.query(Task.project_id, Task.status, func.count())
                               .filter(Task.project_id.in_(ids)).group_by(Task.project_id, Task.status)):
        tasks[pid] += count
        if status == STATUS_DONE:
            done[pid] += count
        elif status == STATUS_BLOCKED:
            blocked[pid] += count
    members = defaultdict(list)
    for pid, username in (db.query(ProjectMember.project_id, ProjectMember.username)
                          .filter(ProjectMember.project_id.in_(ids)).order_by(ProjectMember.username)):
        members[pid].append(username)

    result = []
    for p in projects:
        budget, used = p.initial_budget or 0.0, spent.get(p.id) or 0.0
        total, completed = tasks[p.id], done[p.id]
        result.append(ProjectSummary(
            id=p.id, name=p.name, initial_budget=budget, members=members[p.id],
            spent=used, remaining=budget - used, spent_pct=used / budget * 100 if budget > 0 else 0.0,
            tasks=total, done=completed, open=total - completed,
            done_pct=completed / total * 100 if total else 100.0, blocked=blocked[p.id],
            files=files.get(p.id, 0),
        ))
    return result


def _validate_members(db: Session, usernames: list[str]) -> list[str]:
    usernames = sorted(set(usernames))
    known = {u for (u,) in db.query(User.username).filter(User.username.in_(usernames), User.is_active.is_(True))}
    unknown = set(usernames) - known
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown or inactive users: {', '.join(sorted(unknown))}")
    return usernames


def _set_members(project: Project, usernames: list[str], editor: User):
    if not can_see_all(editor) and editor.username not in usernames:
        usernames = usernames + [editor.username]  # מי שיוצר/עורך לא מוציא את עצמו בטעות מהפרויקט
    project.members = [ProjectMember(username=u) for u in usernames]


# =========================================================
# פרויקטים
# =========================================================
@router.get("/projects/", response_model=list[ProjectSummary])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_summaries(db, visible_projects_query(db, user).order_by(Project.id).all())


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id)
    summary = build_summaries(db, [project])[0]
    file_list = []
    for f in project.files:
        sig = create_file_token(f.id)
        file_list.append({"id": f.id, "filename": f.filename, "uploaded_by": f.uploaded_by, "size": f.size,
                          "work_log_id": f.work_log_id, "view_url": f"/files/{f.id}/view?sig={sig}",
                          "download_url": f"/files/{f.id}/download?sig={sig}"})
    return ProjectDetail(
        **summary.model_dump(),
        task_list=[task_out(t) for t in project.tasks],
        expense_list=[{"id": e.id, "catalog_id": e.catalog_id, "title": e.title, "final_price": e.final_price}
                      for e in project.expenses],
        file_list=file_list,
    )


@router.post("/projects/", response_model=ProjectSummary, status_code=201)
def create_project(req: ProjectCreate, user: User = Depends(require_permission(PERM_CREATE_PROJECT)),
                   db: Session = Depends(get_db)):
    project = Project(name=req.name, initial_budget=req.initial_budget)
    _set_members(project, _validate_members(db, req.members), user)
    db.add(project)
    db.commit()
    return build_summaries(db, [project])[0]


@router.patch("/projects/{project_id}", response_model=ProjectSummary)
def update_project(project_id: int, req: ProjectUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id, PERM_EDIT_PROJECT)
    if req.name is not None:
        project.name = req.name.strip()
    if req.initial_budget is not None:
        project.initial_budget = req.initial_budget
    if req.members is not None:
        _set_members(project, _validate_members(db, req.members), user)
    db.commit()
    return build_summaries(db, [project])[0]


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id, PERM_DELETE_PROJECT)
    stored = [f.storage_path for f in project.files]
    name = project.name
    db.delete(project)  # ה-cascade מוחק גם משימות, הוצאות, קבצים ושותפים
    db.commit()
    audit.info("Project deleted id=%s name=%s files=%s by=%s", project_id, name, len(stored), user.username)
    for path in stored:  # מחיקה מהדיסק רק אחרי שהמחיקה במסד הצליחה
        storage.delete_stored(path)


# =========================================================
# משימות
# =========================================================
def task_out(task: Task) -> dict:
    return {"id": task.id, "title": task.title, "assigned_to": task.assigned_to, "priority": task.priority,
            "status": task.status, "blocked_reason": task.blocked_reason, "blocked_since": task.blocked_since}


def _get_task(db: Session, project: Project, task_id: str) -> Task:
    task = db.query(Task).filter_by(id=task_id, project_id=project.id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/projects/{project_id}/tasks/", status_code=201)
def add_task(project_id: int, req: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id, PERM_MANAGE_TASKS)
    if req.assigned_to not in project.member_names:
        raise HTTPException(status_code=422, detail="Assignee must be a member of the project")
    task = Task(id=str(uuid.uuid4()), project_id=project.id, title=req.title, assigned_to=req.assigned_to,
                priority=req.priority)
    db.add(task)
    db.commit()
    return {"id": task.id}


@router.patch("/projects/{project_id}/tasks/{task_id}")
def update_task_status(project_id: int, task_id: str, req: StatusUpdate, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id)
    task = _get_task(db, project, task_id)
    _require_status_permission(user, task)
    _set_status(task, req.status, req.blocked_reason)
    db.commit()
    return {"status": task.status}


def _require_status_permission(user: User, task: Task):
    own_task = task.assigned_to == user.username and has_permission(user.role, PERM_UPDATE_OWN_TASKS)
    if not (has_permission(user.role, PERM_MANAGE_TASKS) or own_task):
        raise HTTPException(status_code=403, detail="Permission denied")


def _set_status(task: Task, status: str, blocked_reason: str | None):
    if status == STATUS_BLOCKED:
        reason = (blocked_reason or "").strip() or (task.blocked_reason if task.status == STATUS_BLOCKED else "")
        if not reason:
            raise HTTPException(status_code=422, detail=f"Blocked reason is required: {task.title}")
        if task.status != STATUS_BLOCKED:
            task.blocked_since = dt.date.today()  # עדכון הסיבה לא מאפס את מספר הימים
        task.blocked_reason = reason
    else:
        task.blocked_reason, task.blocked_since = None, None
    task.status = status


@router.patch("/projects/{project_id}/tasks/")
def bulk_update_tasks(project_id: int, req: TaskBulkUpdate, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """עדכון כמה משימות בבת אחת (עריכה בטבלה). הכל או כלום: אם שינוי אחד לא תקין - שום דבר לא נשמר.
    שינוי כותרת, אחראי או דחיפות דורש הרשאת ניהול משימות; שינוי סטטוס - כמו בעדכון בודד."""
    project = get_project_for(db, user, project_id)
    members = set(project.member_names)
    tasks = {t.id: t for t in db.query(Task).filter(Task.project_id == project.id,
                                                     Task.id.in_([u.id for u in req.updates]))}
    changed = 0
    for update in req.updates:
        task = tasks.get(update.id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        fields = {name: getattr(update, name) for name in ("title", "assigned_to", "priority")
                  if getattr(update, name) is not None and getattr(update, name) != getattr(task, name)}
        if fields:
            require(user, PERM_MANAGE_TASKS)
            if "assigned_to" in fields and fields["assigned_to"] not in members:
                raise HTTPException(status_code=422, detail="Assignee must be a member of the project")
            for name, value in fields.items():
                setattr(task, name, value.strip() if isinstance(value, str) else value)
        new_reason = (update.blocked_reason or "").strip()
        status_changed = update.status is not None and update.status != task.status
        reason_changed = task.status == STATUS_BLOCKED and new_reason and new_reason != task.blocked_reason
        if status_changed or reason_changed:
            _require_status_permission(user, task)
            _set_status(task, update.status or task.status, new_reason)
        changed += bool(fields or status_changed or reason_changed)
    db.commit()
    return {"updated": changed}


@router.delete("/projects/{project_id}/tasks/{task_id}", status_code=204)
def delete_task(project_id: int, task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id, PERM_MANAGE_TASKS)
    db.delete(_get_task(db, project, task_id))
    db.commit()


# =========================================================
# הוצאות
# =========================================================
@router.post("/projects/{project_id}/expenses/", status_code=201)
def add_expense(project_id: int, req: ExpenseCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id, PERM_MANAGE_BUDGET)
    item = DEKEL_CATALOG[req.catalog_id]
    expense = Expense(project_id=project.id, catalog_id=req.catalog_id, title=item["title"],
                      final_price=req.custom_price if req.custom_price is not None else item["default_price"])
    db.add(expense)
    db.commit()
    return {"id": expense.id}


@router.delete("/projects/{project_id}/expenses/{expense_id}", status_code=204)
def delete_expense(project_id: int, expense_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id, PERM_MANAGE_BUDGET)
    expense = db.query(Expense).filter_by(id=expense_id, project_id=project.id).first()
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()
