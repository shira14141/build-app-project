"""נקודת הכניסה של השרת.

הרצה:  uvicorn main:app --reload
תיעוד API אינטראקטיבי:  http://127.0.0.1:8000/docs

הקוד עצמו נמצא בחבילה server/:
  config.py         - הגדרות (מסד, תיקיות, מפתח חתימה, מגבלות) - הכל ניתן לדריסה במשתני סביבה
  db.py             - חיבור למסד (SQLite או PostgreSQL)
  models.py         - טבלאות
  schemas.py        - ולידציה של קלט ומבנה תשובות
  auth.py           - סיסמאות, טוקנים והרשאות
  ratelimit.py      - נעילה זמנית אחרי ניסיונות התחברות כושלים
  storage.py        - שמירת קבצים בדיסק
  logging_setup.py  - לוגים לקונסול ולקובץ logs/buildapp.log
  migrate.py        - מיגרציות אוטומטיות בעלייה (migrations/)
  routers/          - הנתיבים לפי נושא
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from server.config import SLOW_REQUEST_MS
from server.db import engine
from server.logging_setup import setup_logging
from server.migrate import upgrade_database
from server.routers import auth_users, dashboard, files, personal, projects, work_logs

setup_logging()
log = logging.getLogger("buildapp")
request_log = logging.getLogger("buildapp.request")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upgrade_database()
    log.info("Server started (database: %s)", engine.url.render_as_string(hide_password=True))
    yield


app = FastAPI(title="Construction Manager Pro", lifespan=lifespan)
for module in (auth_users, projects, files, personal, dashboard, work_logs):
    app.include_router(module.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """שורת לוג לכל בקשה + מזהה בקשה (X-Request-ID) שמופיע גם בתשובה, כדי לקשר בין שגיאה שמשתמש
    ראה לבין השורה בלוג. נרשם רק הנתיב - בלי query string, שבו יושבות חתימות של קישורי קבצים."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error rid=%s %s %s", request_id, request.method, request.url.path)
        response = JSONResponse(status_code=500, content={"detail": "Internal server error",
                                                          "request_id": request_id})
    elapsed_ms = (time.perf_counter() - start) * 1000
    level = logging.WARNING if elapsed_ms > SLOW_REQUEST_MS or response.status_code >= 500 else logging.INFO
    request_log.log(level, "%s %s -> %s %.0fms user=%s rid=%s", request.method, request.url.path,
                    response.status_code, elapsed_ms, getattr(request.state, "username", "-"), request_id)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", tags=["system"])
def health():
    """בדיקת חיות - כולל חיבור אמיתי למסד (מתאים לניטור או ל-load balancer)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        log.exception("Health check: database unavailable")
        return JSONResponse(status_code=503, content={"status": "error", "database": "unavailable"})
    return {"status": "ok", "database": "ok"}
