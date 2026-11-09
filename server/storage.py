"""אחסון קבצים בדיסק (במקום BLOB בתוך SQLite).

הקבצים נשמרים ב-UPLOAD_DIR/<project_id>/<file_id>. ההעלאה נכתבת בחלקים, כך שקובץ גדול
לא נטען כולו לזיכרון, ונעצרת ברגע שעוברים את מגבלת הגודל.
"""
from pathlib import Path

from fastapi import HTTPException, UploadFile

from server.config import MAX_UPLOAD_MB, UPLOAD_DIR

CHUNK_SIZE = 1024 * 1024
MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def absolute_path(storage_path: str) -> Path:
    path = (UPLOAD_DIR / storage_path).resolve()
    if UPLOAD_DIR.resolve() not in path.parents:  # הגנה מפני נתיב שבורח מתיקיית ההעלאות
        raise HTTPException(status_code=404)
    return path


def save_upload(upload: UploadFile, project_id: int, file_id: str) -> tuple[str, int]:
    storage_path = f"{project_id}/{file_id}"
    target = absolute_path(storage_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := upload.file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(status_code=413, detail=f"File larger than {MAX_UPLOAD_MB}MB")
                out.write(chunk)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return storage_path, size


def delete_stored(storage_path: str):
    if storage_path:
        absolute_path(storage_path).unlink(missing_ok=True)
