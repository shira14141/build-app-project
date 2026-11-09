"""הגדרות השרת. כל ערך אפשר לדרוס במשתנה סביבה."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.environ.get("BUILDAPP_DB_URL", f"sqlite:///{(BASE_DIR / 'construction.db').as_posix()}")
UPLOAD_DIR = Path(os.environ.get("BUILDAPP_UPLOAD_DIR", BASE_DIR / "uploads"))

LOG_DIR = Path(os.environ.get("BUILDAPP_LOG_DIR", BASE_DIR / "logs"))
LOG_LEVEL = os.environ.get("BUILDAPP_LOG_LEVEL", "INFO").upper()
SLOW_REQUEST_MS = int(os.environ.get("BUILDAPP_SLOW_REQUEST_MS", "1000"))

MAX_LOGIN_FAILURES = int(os.environ.get("BUILDAPP_MAX_LOGIN_FAILURES", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("BUILDAPP_LOGIN_LOCKOUT_MINUTES", "10"))

MAX_UPLOAD_MB = int(os.environ.get("BUILDAPP_MAX_UPLOAD_MB", "25"))
ACCESS_TOKEN_HOURS = int(os.environ.get("BUILDAPP_TOKEN_HOURS", "8"))
FILE_LINK_MINUTES = int(os.environ.get("BUILDAPP_FILE_LINK_MINUTES", "60"))


def _load_secret_key():
    """מפתח החתימה של הטוקנים. ממשתנה סביבה, ואם אין - נוצר פעם אחת ונשמר בקובץ מקומי
    (כדי שהתחברויות לא יתנתקו בכל הפעלה מחדש של השרת)."""
    if os.environ.get("BUILDAPP_SECRET"):
        return os.environ["BUILDAPP_SECRET"]
    key_file = BASE_DIR / ".secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return key_file.read_text(encoding="utf-8").strip()


SECRET_KEY = _load_secret_key()
