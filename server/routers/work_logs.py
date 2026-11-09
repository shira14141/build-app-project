"""יומן עבודה: דיווח יומי מהאתר לכל פרויקט.

כל שותף עם הרשאת דיווח (מנהלים וקבלנים) יכול לדווח; כל השותפים רואים את ההיסטוריה.
מחיקה: מי שכתב את הדיווח, או מנהל. תמונות נשמרות כקבצי פרויקט רגילים עם work_log_id.
"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from constants import PERM_MANAGE_WORK_LOGS, PERM_WRITE_WORK_LOG, has_permission
from server import storage
from server.auth import create_file_token, get_current_user, get_project_for
from server.db import get_db
from server.logging_setup import audit
from server.models import File, User, WorkLog
from server.schemas import WorkLogCreate, WorkLogOut

router = APIRouter(tags=["work logs"])


def _photo_out(f: File) -> dict:
    sig = create_file_token(f.id)
    return {"id": f.id, "filename": f.filename, "uploaded_by": f.uploaded_by, "size": f.size,
            "work_log_id": f.work_log_id, "view_url": f"/files/{f.id}/view?sig={sig}",
            "download_url": f"/files/{f.id}/download?sig={sig}"}


@router.get("/projects/{project_id}/work_logs", response_model=list[WorkLogOut])
def list_work_logs(project_id: int, limit: int = Query(30, ge=1, le=200), user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id)
    logs = (db.query(WorkLog).filter_by(project_id=project.id)
            .order_by(WorkLog.log_date.desc(), WorkLog.id.desc()).limit(limit).all())
    photos = {}
    if logs:
        for f in (db.query(File).filter(File.work_log_id.in_([log.id for log in logs]))
                  .order_by(File.filename)):
            photos.setdefault(f.work_log_id, []).append(_photo_out(f))
    return [WorkLogOut(id=log.id, project_id=log.project_id, log_date=log.log_date, author=log.author,
                       weather=log.weather, crew=log.crew or [],
                       total_workers=sum(c.get("workers", 0) for c in (log.crew or [])),
                       work_done=log.work_done, issues=log.issues, created_at=log.created_at,
                       photos=photos.get(log.id, [])) for log in logs]


@router.post("/projects/{project_id}/work_logs", status_code=201)
def create_work_log(project_id: int, req: WorkLogCreate, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id, PERM_WRITE_WORK_LOG)
    log = WorkLog(project_id=project.id, log_date=req.log_date, author=user.username, weather=req.weather,
                  crew=[c.model_dump() for c in req.crew if c.workers > 0], work_done=req.work_done,
                  issues=(req.issues or "").strip() or None,
                  created_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))
    db.add(log)
    db.commit()
    audit.info("Work log created id=%s project=%s date=%s by=%s", log.id, project.id, log.log_date, user.username)
    return {"id": log.id}


@router.delete("/projects/{project_id}/work_logs/{log_id}", status_code=204)
def delete_work_log(project_id: int, log_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id)
    log = db.query(WorkLog).filter_by(id=log_id, project_id=project.id).first()
    if log is None:
        raise HTTPException(status_code=404, detail="Work log not found")
    if log.author != user.username and not has_permission(user.role, PERM_MANAGE_WORK_LOGS):
        raise HTTPException(status_code=403, detail="Only the author or a manager can delete this work log")
    photos = db.query(File).filter_by(work_log_id=log.id).all()
    stored = [f.storage_path for f in photos]
    for f in photos:
        db.delete(f)
    db.delete(log)
    db.commit()
    for path in stored:
        storage.delete_stored(path)
    audit.info("Work log deleted id=%s project=%s photos=%s by=%s", log_id, project.id, len(stored), user.username)
