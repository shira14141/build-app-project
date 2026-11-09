"""חיבור למסד. עובד עם SQLite (ברירת מחדל) ועם PostgreSQL - לפי BUILDAPP_DB_URL.

דוגמה ל-PostgreSQL:  postgresql+psycopg://user:password@localhost:5432/buildapp
(דורש pip install "psycopg[binary]" - ראו README)
"""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from server.config import DATABASE_URL

IS_SQLITE = make_url(DATABASE_URL).get_backend_name() == "sqlite"

if IS_SQLITE:
    # SQLite: אותו חיבור משמש כמה threads של השרת
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    # SQLite לא אוכף מפתחות זרים כברירת מחדל - מפעילים בכל חיבור (ב-PostgreSQL זה תמיד פעיל)
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
else:
    # שרת מסד אמיתי: pool של חיבורים, ובדיקה שהחיבור חי לפני שימוש (אחרי הפעלה מחדש של המסד וכו')
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
