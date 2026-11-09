"""בדיקות מיגרציה: מסד ישן (לפני שלב 3) עובר המרה מלאה בלי לאבד נתונים, אפשר לחזור אחורה,
וכלי ההעתקה בין מסדים עובד. כל בדיקה רצה בתהליך נפרד עם מסד ותיקיות משלה."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
HEAD = "0003"  # הגרסה האחרונה בתיקייה migrations/versions
BLOB = b"%PDF-1.4 legacy file \x00\x01\x02"


def make_legacy_db(path: Path):
    """מסד במבנה המקורי: שותפים כ-JSON, קובץ כ-BLOB, ושותף שלא ברשימת המשתמשים."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR, initial_budget FLOAT, partners VARCHAR);
        CREATE TABLE tasks (id VARCHAR PRIMARY KEY, project_id INTEGER REFERENCES projects(id), title VARCHAR,
                            assigned_to VARCHAR, priority INTEGER, status VARCHAR);
        CREATE TABLE expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER REFERENCES projects(id),
                               catalog_id VARCHAR, title VARCHAR, final_price FLOAT);
        CREATE TABLE files (id VARCHAR PRIMARY KEY, project_id INTEGER REFERENCES projects(id), filename VARCHAR,
                            uploaded_by VARCHAR, data BLOB);
        CREATE TABLE personal_tasks (id VARCHAR PRIMARY KEY, title VARCHAR, assigned_to VARCHAR, priority INTEGER,
                                     status VARCHAR, date VARCHAR);
    """)
    conn.execute("INSERT INTO projects VALUES (7, 'מגדל', 1000, ?)",
                 (json.dumps(["דנה האדריכלית", "שותף חיצוני"], ensure_ascii=False),))
    conn.execute("INSERT INTO tasks VALUES ('t1', 7, 'יסודות', 'דנה האדריכלית', 4, 'ממתין')")
    conn.execute("INSERT INTO expenses (project_id, catalog_id, title, final_price) VALUES (7, '101', 'בטון', 350)")
    conn.execute("INSERT INTO files VALUES ('f1', 7, 'תוכנית.pdf', 'שירה', ?)", (BLOB,))
    conn.execute("INSERT INTO personal_tasks VALUES ('p1', 'פגישה', 'שירה', 3, 'ממתין', '2026-12-01')")
    conn.commit()
    conn.close()


def run(code, tmp: Path, db_name="legacy.db"):
    env = {**os.environ, "BUILDAPP_DB_URL": f"sqlite:///{(tmp / db_name).as_posix()}",
           "BUILDAPP_UPLOAD_DIR": str(tmp / "uploads"), "BUILDAPP_SECRET": "x" * 40, "PYTHONIOENCODING": "utf-8"}
    res = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_DIR, env=env, capture_output=True, text=True,
                         encoding="utf-8")
    assert res.returncode == 0, res.stderr
    return res


UPGRADE = "from server.migrate import upgrade_database; upgrade_database()"
DOWNGRADE = ("from alembic import command; from server.migrate import _alembic_config; "
             "command.downgrade(_alembic_config(), '0001')")


def test_legacy_database_upgrade_preserves_data(tmp_path):
    make_legacy_db(tmp_path / "legacy.db")
    run(UPGRADE, tmp_path)
    c = sqlite3.connect(tmp_path / "legacy.db")
    assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD,)
    # שותפים -> טבלה; שותף לא מוכר נוצר כמשתמש מושבת
    assert sorted(r[0] for r in c.execute("SELECT username FROM project_members WHERE project_id=7")) == \
        sorted(["דנה האדריכלית", "שותף חיצוני"])
    assert c.execute("SELECT is_active FROM users WHERE username='שותף חיצוני'").fetchone() == (0,)
    assert c.execute("SELECT must_change_password FROM users WHERE username='שירה'").fetchone() == (1,)
    # קובץ -> דיסק, זהה בייט-לבייט
    storage_path, size, content_type = c.execute("SELECT storage_path, size, content_type FROM files").fetchone()
    assert (tmp_path / "uploads" / storage_path).read_bytes() == BLOB
    assert size == len(BLOB) and content_type == "application/pdf"
    assert "data" not in [r[1] for r in c.execute("PRAGMA table_info(files)")]
    # שאר הנתונים לא נגעו
    assert c.execute("SELECT title, status FROM tasks").fetchone() == ("יסודות", "ממתין")
    assert c.execute("SELECT final_price FROM expenses").fetchone() == (350.0,)
    assert c.execute("SELECT title FROM personal_tasks").fetchone() == ("פגישה",)
    c.close()
    assert list(tmp_path.glob("legacy.backup-*.db")), "a backup must be created before upgrading"


def test_upgrade_is_idempotent_and_downgrade_restores(tmp_path):
    make_legacy_db(tmp_path / "legacy.db")
    run(UPGRADE, tmp_path)
    run(UPGRADE, tmp_path)  # הרצה שנייה - לא עושה כלום
    assert len(list(tmp_path.glob("legacy.backup-*.db"))) == 1
    run(DOWNGRADE, tmp_path)
    c = sqlite3.connect(tmp_path / "legacy.db")
    assert c.execute("SELECT data FROM files").fetchone()[0] == BLOB
    assert sorted(json.loads(c.execute("SELECT partners FROM projects").fetchone()[0])) == \
        sorted(["דנה האדריכלית", "שותף חיצוני"])
    assert "users" not in [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    c.close()


def test_fresh_database_is_created_from_scratch(tmp_path):
    run(UPGRADE, tmp_path, db_name="fresh.db")
    c = sqlite3.connect(tmp_path / "fresh.db")
    assert c.execute("SELECT count(*) FROM users").fetchone() == (6,)
    assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD,)
    c.close()
    assert not list(tmp_path.glob("*.backup-*.db")), "nothing to back up for a brand-new database"


def test_copy_database_tool(tmp_path):
    make_legacy_db(tmp_path / "legacy.db")
    run(UPGRADE, tmp_path)
    run(UPGRADE, tmp_path, db_name="target.db")
    src, dst = (f"sqlite:///{(tmp_path / n).as_posix()}" for n in ("legacy.db", "target.db"))
    run(f"from tools.copy_database import copy_database; copy_database({src!r}, {dst!r})", tmp_path)
    a, b = sqlite3.connect(tmp_path / "legacy.db"), sqlite3.connect(tmp_path / "target.db")
    for table in ["users", "projects", "project_members", "tasks", "expenses", "work_logs", "files",
                  "personal_tasks"]:
        assert sorted(a.execute(f"SELECT * FROM {table}").fetchall()) == \
            sorted(b.execute(f"SELECT * FROM {table}").fetchall()), table
    a.close()
    b.close()
    # הרצה שנייה נעצרת - היעד כבר לא ריק
    env_code = f"from tools.copy_database import copy_database; copy_database({src!r}, {dst!r})"
    res = subprocess.run([sys.executable, "-c", env_code], cwd=PROJECT_DIR, capture_output=True, text=True,
                         encoding="utf-8", env={**os.environ, "BUILDAPP_SECRET": "x" * 40, "PYTHONIOENCODING": "utf-8"})
    assert res.returncode != 0 and "not empty" in (res.stderr + res.stdout)


def test_0003_downgrade_turns_blocked_into_in_progress(tmp_path):
    make_legacy_db(tmp_path / "legacy.db")
    run(UPGRADE, tmp_path)
    c = sqlite3.connect(tmp_path / "legacy.db")
    c.execute("UPDATE tasks SET status='חסום', blocked_reason='אישור', blocked_since='2026-11-01'")
    c.commit()
    c.close()
    run("from alembic import command; from server.migrate import _alembic_config; "
        "command.downgrade(_alembic_config(), '0002')", tmp_path)
    c = sqlite3.connect(tmp_path / "legacy.db")
    assert c.execute("SELECT status FROM tasks").fetchone() == ("בתהליך",)
    assert "blocked_reason" not in [r[1] for r in c.execute("PRAGMA table_info(tasks)")]
    assert "work_logs" not in [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    c.close()
    run(UPGRADE, tmp_path)  # וחזרה קדימה
    assert sqlite3.connect(tmp_path / "legacy.db").execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD,)
