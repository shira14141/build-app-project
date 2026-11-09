"""משתמשים והרשאות, טבלת שותפים לפרויקט, וקבצים בדיסק במקום במסד.

מה המיגרציה עושה עם הנתונים הקיימים:
1. יוצרת טבלת users ומכניסה את ששת המשתמשים שהיו מקודדים בקוד, עם הסיסמאות הישנות
   (מוצפנות ב-bcrypt) וחובה להחליף סיסמה בכניסה הראשונה.
2. מעבירה את עמודת ה-JSON projects.partners לטבלת project_members.
3. כותבת את תוכן כל קובץ מ-files.data לתיקיית ההעלאות, ומוחקת את עמודת ה-BLOB.
4. מוסיפה אינדקסים על העמודות שמסננים לפיהן.

Revision ID: 0002
Revises: 0001
"""
import json
import secrets

import bcrypt
import sqlalchemy as sa
from alembic import context, op

from server.config import UPLOAD_DIR

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# (שם משתמש, סיסמה נוכחית, תפקיד). שירה - מנהלת מערכת; יוסי ומשה - מנהלי פרויקט; השאר - בעלי מקצוע.
SEED_USERS = [
    ("שירה", "admin", "admin"),
    ("יוסי הקבלן", "1234", "manager"),
    ("משה מפקח הבנייה", "1234", "manager"),
    ("דנה האדריכלית", "1234", "contractor"),
    ("אבי אינסטלטור", "1234", "contractor"),
    ("רוני קבלן חשמל", "1234", "contractor"),
]


def _hash(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def upgrade():
    # במצב offline (alembic upgrade head --sql) אין חיבור ואין נתונים קיימים - רק מבנה ומשתמשי הבסיס
    conn = None if context.is_offline_mode() else op.get_bind()

    # ---- 1. משתמשים ----
    users = op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String, nullable=False, unique=True),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.bulk_insert(users, [{"username": u, "password_hash": _hash(p), "role": r, "must_change_password": True,
                            "is_active": True} for u, p, r in SEED_USERS])
    known_users = {u for u, _, _ in SEED_USERS}

    # ---- 2. שותפים: JSON -> טבלה ----
    members = op.create_table(
        "project_members",
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("username", sa.String, sa.ForeignKey("users.username", ondelete="CASCADE"), primary_key=True),
    )
    member_rows = []
    existing_projects = conn.execute(sa.text("SELECT id, partners FROM projects")).fetchall() if conn else []
    for project_id, partners in existing_projects:
        for name in sorted(set(json.loads(partners or "[]"))):
            if name not in known_users:
                # שותף שאינו ברשימה הידועה: נוצר כמשתמש מושבת עם סיסמה אקראית, כדי לא לאבד את השיוך.
                # מנהל המערכת יכול להפעיל אותו ולאפס לו סיסמה בדף ניהול המשתמשים.
                op.bulk_insert(users, [{"username": name, "password_hash": _hash(secrets.token_urlsafe(16)),
                                        "role": "contractor", "must_change_password": True, "is_active": False}])
                known_users.add(name)
            member_rows.append({"project_id": project_id, "username": name})
    if member_rows:
        op.bulk_insert(members, member_rows)
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("partners")

    # ---- 3. קבצים: BLOB -> דיסק ----
    with op.batch_alter_table("files") as batch:
        batch.add_column(sa.Column("storage_path", sa.String))
        batch.add_column(sa.Column("size", sa.Integer))
        batch.add_column(sa.Column("content_type", sa.String))
    import mimetypes
    existing_files = conn.execute(sa.text("SELECT id, project_id, filename, data FROM files")).fetchall() if conn else []
    for file_id, project_id, filename, data in existing_files:
        storage_path = f"{project_id}/{file_id}"
        target = UPLOAD_DIR / storage_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data or b"")
        conn.execute(sa.text("UPDATE files SET storage_path=:p, size=:s, content_type=:c WHERE id=:i"),
                     {"p": storage_path, "s": len(data or b""), "i": file_id,
                      "c": mimetypes.guess_type(filename or "")[0] or "application/octet-stream"})
    with op.batch_alter_table("files") as batch:
        batch.drop_column("data")

    # ---- 4. אינדקסים ----
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_expenses_project_id", "expenses", ["project_id"])
    op.create_index("ix_files_project_id", "files", ["project_id"])
    op.create_index("ix_personal_tasks_assigned_to", "personal_tasks", ["assigned_to"])


def downgrade():
    conn = op.get_bind()
    for name in ["ix_personal_tasks_assigned_to", "ix_files_project_id", "ix_expenses_project_id",
                 "ix_tasks_project_id"]:
        op.drop_index(name)

    with op.batch_alter_table("files") as batch:
        batch.add_column(sa.Column("data", sa.LargeBinary))
    for file_id, storage_path in conn.execute(sa.text("SELECT id, storage_path FROM files")).fetchall():
        path = UPLOAD_DIR / (storage_path or "")
        data = path.read_bytes() if storage_path and path.is_file() else b""
        conn.execute(sa.text("UPDATE files SET data=:d WHERE id=:i"), {"d": data, "i": file_id})
    with op.batch_alter_table("files") as batch:
        batch.drop_column("content_type")
        batch.drop_column("size")
        batch.drop_column("storage_path")

    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("partners", sa.String))
    partners = {}
    for project_id, username in conn.execute(sa.text("SELECT project_id, username FROM project_members")):
        partners.setdefault(project_id, []).append(username)
    for (project_id,) in conn.execute(sa.text("SELECT id FROM projects")).fetchall():
        conn.execute(sa.text("UPDATE projects SET partners=:p WHERE id=:i"),
                     {"p": json.dumps(partners.get(project_id, []), ensure_ascii=False), "i": project_id})

    op.drop_table("project_members")
    op.drop_table("users")
