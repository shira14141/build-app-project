import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.config import DATABASE_URL  # noqa: E402

# אפשר לדרוס את הכתובת מהשורה: alembic -x db_url=postgresql://... upgrade head --sql
DB_URL = context.get_x_argument(as_dictionary=True).get("db_url", DATABASE_URL)
IS_SQLITE = make_url(DB_URL).get_backend_name() == "sqlite"


def run_migrations_offline():
    """מייצר קובץ SQL במקום להריץ (alembic upgrade head --sql) - שימושי ל-DBA או לבדיקת DDL."""
    context.configure(url=DB_URL, literal_binds=True, render_as_batch=IS_SQLITE)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(DB_URL)
    with engine.connect() as connection:
        if IS_SQLITE:
            # ב-SQLite שינוי עמודות נעשה ע"י בנייה מחדש של הטבלה, ומפתחות זרים פעילים היו
            # מוחקים/חוסמים שורות קשורות באמצע התהליך - לכן מכבים אותם בזמן המיגרציה
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            # SQLAlchemy 2 פותח טרנזקציה אוטומטית גם ל-PRAGMA; סוגרים אותה כדי ש-Alembic ינהל
            # (ויבצע commit ל) טרנזקציה משלו - אחרת השינויים מתבטלים בסגירת החיבור
            connection.commit()
        context.configure(connection=connection, render_as_batch=IS_SQLITE)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
