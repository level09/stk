"""stk durable jobs: the stk_job table that `stk worker` drains."""

import sqlalchemy as sa
from alembic import op

revision = "stk_0002"
down_revision = "stk_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stk_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(), nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stk_job")),
    )
    with op.batch_alter_table("stk_job", schema=None) as batch_op:
        batch_op.create_index(
            "ix_stk_job_status_run_after", ["status", "run_after"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("stk_job", schema=None) as batch_op:
        batch_op.drop_index("ix_stk_job_status_run_after")
    op.drop_table("stk_job")
