"""הרצת מיגרציות אוטומטית בעליית השרת, כולל גיבוי של קובץ המסד לפני כל שינוי מבנה."""
import datetime as dt
import logging
import shutil
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from server.config import BASE_DIR, DATABASE_URL

log = logging.getLogger("buildapp.migrate")
INITIAL_REVISION = "0001"


def _alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations").replace("%", "%%"))
    return cfg


def _backup_sqlite():
    url = make_url(DATABASE_URL)
    if not url.drivername.startswith("sqlite") or not url.database:
        return None
    db_file = Path(url.database)
    if not db_file.exists():
        return None
    backup = db_file.with_name(f"{db_file.stem}.backup-{dt.datetime.now():%Y%m%d-%H%M%S}{db_file.suffix}")
    shutil.copy2(db_file, backup)
    return backup


def upgrade_database():
    cfg = _alembic_config()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        current = MigrationContext.configure(conn).get_current_revision()
    engine.dispose()

    if current is None and "projects" in tables:
        # מסד שנוצר לפני שהיו מיגרציות - המבנה שלו זהה ל-0001
        command.stamp(cfg, INITIAL_REVISION)
        current = INITIAL_REVISION
    if current == head:
        return
    if tables:
        backup = _backup_sqlite()
        if backup:
            log.warning("Database schema upgrade %s -> %s. Backup saved to %s", current, head, backup)
    command.upgrade(cfg, "head")
