"""העתקת כל הנתונים ממסד אחד לאחר - למשל מ-SQLite ל-PostgreSQL.

שלבים:
  1. ליצור מסד ריק ב-PostgreSQL ולהריץ עליו מיגרציות:
       set BUILDAPP_DB_URL=postgresql+psycopg://user:pass@localhost:5432/buildapp
       python -m alembic upgrade head
  2. להעתיק את הנתונים:
       python tools/copy_database.py --source sqlite:///construction.db ^
                                     --target postgresql+psycopg://user:pass@localhost:5432/buildapp
  3. לעדכן את BUILDAPP_DB_URL של השרת לכתובת החדשה ולהפעיל אותו.

הסקריפט:
  - מוודא ששני המסדים באותה גרסת מיגרציה, ושהיעד ריק (חוץ ממשתמשי הבסיס שהמיגרציה יצרה, שמוחלפים).
  - מעתיק את כל הטבלאות לפי סדר המפתחות הזרים, בטרנזקציה אחת (הכל או כלום).
  - ב-PostgreSQL מעדכן את מוני ה-id (sequences) כדי שרשומות חדשות לא יתנגשו.
קבצים מצורפים לא נמצאים במסד אלא בתיקיית uploads/ - אותה מעתיקים/משאירים כמו שהיא.
"""
import argparse
import sys

from alembic.runtime.migration import MigrationContext
from sqlalchemy import MetaData, create_engine, func, select, text

# סדר שמכבד מפתחות זרים: קודם טבלאות שאחרות מצביעות אליהן
TABLES = ["users", "projects", "project_members", "tasks", "expenses", "work_logs", "files", "personal_tasks"]
SERIAL_TABLES = ["users", "projects", "expenses", "work_logs"]  # טבלאות עם id מספרי אוטומטי
BATCH = 500


def revision(engine):
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def copy_database(source_url, target_url, log=print):
    source, target = create_engine(source_url), create_engine(target_url)
    src_rev, dst_rev = revision(source), revision(target)
    if src_rev is None or src_rev != dst_rev:
        raise SystemExit(f"Migration versions differ (source={src_rev}, target={dst_rev}). "
                         "Run 'alembic upgrade head' on both databases first.")

    src_meta, dst_meta = MetaData(), MetaData()
    src_meta.reflect(source, only=TABLES)
    dst_meta.reflect(target, only=TABLES)

    with source.connect() as src, target.begin() as dst:
        for name in TABLES[1:]:
            if dst.execute(select(func.count()).select_from(dst_meta.tables[name])).scalar():
                raise SystemExit(f"Target table '{name}' is not empty - refusing to overwrite data.")
        # משתמשי הבסיס שהמיגרציה יצרה ביעד מוחלפים במשתמשים האמיתיים מהמקור
        dst.execute(dst_meta.tables["users"].delete())

        for name in TABLES:
            src_table, dst_table = src_meta.tables[name], dst_meta.tables[name]
            columns = [c.name for c in dst_table.columns]
            result = src.execute(select(*[src_table.c[c] for c in columns]))
            copied = 0
            while rows := result.fetchmany(BATCH):
                dst.execute(dst_table.insert(), [dict(zip(columns, row)) for row in rows])
                copied += len(rows)
            log(f"  {name}: {copied} rows")

        if target.dialect.name == "postgresql":
            for name in SERIAL_TABLES:
                dst.execute(text(f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                                 f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {name}"))
    source.dispose()
    target.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Copy all BuildApp data from one database to another.")
    parser.add_argument("--source", required=True, help="e.g. sqlite:///construction.db")
    parser.add_argument("--target", required=True, help="e.g. postgresql+psycopg://user:pass@host/db")
    args = parser.parse_args(argv)
    print(f"Copying {args.source} -> {args.target.split('@')[-1]}")
    copy_database(args.source, args.target)
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())
