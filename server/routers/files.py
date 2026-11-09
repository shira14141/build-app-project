"""העלאה, צפייה, הורדה ומחיקה של קבצי פרויקט."""
import mimetypes
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File as FileParam, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from constants import PERM_DELETE_ANY_FILE, PERM_UPLOAD_FILES, has_permission
from server import storage
from server.auth import get_current_user, get_project_for, verify_file_token
from server.db import get_db
from server.logging_setup import audit
from server.models import File, User, WorkLog

router = APIRouter(tags=["files"])


@router.post("/projects/{project_id}/files/", status_code=201)
def upload_file(project_id: int, file: UploadFile = FileParam(...), work_log_id: Optional[int] = Form(None),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = get_project_for(db, user, project_id, PERM_UPLOAD_FILES)
    if not file.filename:
        raise HTTPException(status_code=422, detail="Missing file name")
    if work_log_id is not None:
        # תמונה לדיווח: רק לדיווח של אותו פרויקט, ורק מי שכתב אותו
        log = db.query(WorkLog).filter_by(id=work_log_id, project_id=project.id).first()
        if log is None:
            raise HTTPException(status_code=404, detail="Work log not found")
        if log.author != user.username:
            raise HTTPException(status_code=403, detail="Only the author can attach photos to a work log")
    file_id = str(uuid.uuid4())
    storage_path, size = storage.save_upload(file, project.id, file_id)
    content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    try:
        # מי שהעלה = המשתמש המחובר (לא שדה שהלקוח שולח ויכול לזייף)
        db.add(File(id=file_id, project_id=project.id, filename=file.filename, uploaded_by=user.username,
                    storage_path=storage_path, size=size, content_type=content_type, work_log_id=work_log_id))
        db.commit()
    except Exception:
        storage.delete_stored(storage_path)
        raise
    audit.info("File uploaded id=%s project=%s size=%s by=%s", file_id, project.id, size, user.username)
    return {"id": file_id, "size": size}


def _serve(file_id: str, sig: str, db: Session, disposition: str):
    if not verify_file_token(sig, file_id):
        raise HTTPException(status_code=403, detail="Link expired or invalid - refresh the page and try again")
    db_file = db.get(File, file_id)
    if db_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    path = storage.absolute_path(db_file.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File content is missing")
    media_type = db_file.content_type if disposition == "inline" else "application/octet-stream"
    # FileResponse מזרים מהדיסק ומקודד נכון שמות קבצים בעברית
    return FileResponse(path, media_type=media_type, filename=db_file.filename, content_disposition_type=disposition)


@router.get("/files/{file_id}/view")
def view_file(file_id: str, sig: str = Query(...), db: Session = Depends(get_db)):
    return _serve(file_id, sig, db, "inline")


@router.get("/files/{file_id}/download")
def download_file(file_id: str, sig: str = Query(...), db: Session = Depends(get_db)):
    return _serve(file_id, sig, db, "attachment")


@router.delete("/files/{file_id}", status_code=204)
def delete_file(file_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_file = db.get(File, file_id)
    if db_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    get_project_for(db, user, db_file.project_id)
    if db_file.uploaded_by != user.username and not has_permission(user.role, PERM_DELETE_ANY_FILE):
        raise HTTPException(status_code=403, detail="Only the uploader or a manager can delete this file")
    storage_path = db_file.storage_path
    db.delete(db_file)
    db.commit()
    storage.delete_stored(storage_path)
    audit.info("File deleted id=%s project=%s uploader=%s by=%s", file_id, db_file.project_id, db_file.uploaded_by,
               user.username)
