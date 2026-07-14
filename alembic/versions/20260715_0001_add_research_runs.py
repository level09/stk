"""add authenticated Qarina research runs"""

import sqlalchemy as sa

from alembic import op

revision = "20260715_0001"
down_revision = "228ac4e0ebf5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_run_user_id_created_at",
        "research_run",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_run_user_id_created_at", table_name="research_run")
    op.drop_table("research_run")
