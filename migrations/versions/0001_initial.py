"""המבנה המקורי של המסד (לפני שלב 3) - נקודת התחלה.

מסד קיים מסומן כ-0001 בלי להריץ את הקובץ הזה; מסד חדש נבנה ממנו ומשם ממשיך.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String, index=True),
        sa.Column("initial_budget", sa.Float),
        sa.Column("partners", sa.String),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String, primary_key=True, index=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("title", sa.String),
        sa.Column("assigned_to", sa.String),
        sa.Column("priority", sa.Integer),
        sa.Column("status", sa.String),
    )
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("catalog_id", sa.String),
        sa.Column("title", sa.String),
        sa.Column("final_price", sa.Float),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.String, primary_key=True, index=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("filename", sa.String),
        sa.Column("uploaded_by", sa.String),
        sa.Column("data", sa.LargeBinary),
    )
    op.create_table(
        "personal_tasks",
        sa.Column("id", sa.String, primary_key=True, index=True),
        sa.Column("title", sa.String),
        sa.Column("assigned_to", sa.String),
        sa.Column("priority", sa.Integer),
        sa.Column("status", sa.String),
        sa.Column("date", sa.String),
    )


def downgrade():
    for table in ["personal_tasks", "files", "expenses", "tasks", "projects"]:
        op.drop_table(table)
