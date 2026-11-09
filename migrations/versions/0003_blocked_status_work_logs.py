"""סטטוס "חסום" למשימות (סיבה + מאיזה תאריך) ויומן עבודה יומי עם תמונות.

- tasks: עמודות blocked_reason, blocked_since
- work_logs: טבלה חדשה (תאריך, מדווח, מזג אוויר, צוותים כ-JSON, מה בוצע, עיכובים)
- files: עמודה work_log_id - תמונה ששייכת לדיווח (נשאר NULL לקבצים רגילים)
המיגרציה לא משנה נתונים קיימים.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("blocked_reason", sa.String))
        batch.add_column(sa.Column("blocked_since", sa.Date))

    op.create_table(
        "work_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("log_date", sa.Date, nullable=False),
        sa.Column("author", sa.String, nullable=False),
        sa.Column("weather", sa.String),
        sa.Column("crew", sa.JSON, nullable=False),
        sa.Column("work_done", sa.Text, nullable=False),
        sa.Column("issues", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_work_logs_project_id", "work_logs", ["project_id"])
    op.create_index("ix_work_logs_log_date", "work_logs", ["log_date"])

    with op.batch_alter_table("files") as batch:
        batch.add_column(sa.Column("work_log_id", sa.Integer))
        batch.create_foreign_key("fk_files_work_log_id", "work_logs", ["work_log_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_files_work_log_id", ["work_log_id"])


def downgrade():
    # משימות חסומות חוזרות ל"בתהליך" - במבנה הישן אין סטטוס "חסום"
    op.execute("UPDATE tasks SET status = 'בתהליך' WHERE status = 'חסום'")
    with op.batch_alter_table("files") as batch:
        batch.drop_index("ix_files_work_log_id")
        batch.drop_constraint("fk_files_work_log_id", type_="foreignkey")
        batch.drop_column("work_log_id")
    op.drop_index("ix_work_logs_log_date", table_name="work_logs")
    op.drop_index("ix_work_logs_project_id", table_name="work_logs")
    op.drop_table("work_logs")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("blocked_since")
        batch.drop_column("blocked_reason")
