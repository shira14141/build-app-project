"""לוגים: לקונסול ולקובץ מתחלף logs/buildapp.log (עד 5 קבצים של 5MB).

שלושה לוגרים:
  buildapp.request - שורה לכל בקשה: נתיב, קוד תשובה, זמן, משתמש ומזהה בקשה
  buildapp.audit   - פעולות רגישות: התחברות, החלפת סיסמה, ניהול משתמשים, מחיקות
  buildapp.*       - כל השאר (מיגרציות, שגיאות)
אף פעם לא נרשמים סיסמאות, טוקנים או query string (שבו יושבות חתימות של קישורי קבצים).
"""
import logging
from logging.handlers import RotatingFileHandler

from server.config import LOG_DIR, LOG_LEVEL

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_configured = False


def setup_logging():
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(FORMAT)
    file_handler = RotatingFileHandler(LOG_DIR / "buildapp.log", maxBytes=5 * 1024 * 1024, backupCount=5,
                                       encoding="utf-8")
    console_handler = logging.StreamHandler()
    logger = logging.getLogger("buildapp")
    logger.setLevel(LOG_LEVEL)
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.propagate = False
    _configured = True


audit = logging.getLogger("buildapp.audit")
