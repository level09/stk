"""stk notifications: per-user in-app notifications."""

import sqlalchemy as sa
from alembic import op

revision = "stk_0004"
down_revision = "stk_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stk_notification",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_stk_notification_user_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stk_notification")),
    )
    with op.batch_alter_table("stk_notification", schema=None) as batch_op:
        batch_op.create_index(
            "ix_stk_notification_user_id_created_at",
            ["user_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("stk_notification", schema=None) as batch_op:
        batch_op.drop_index("ix_stk_notification_user_id_created_at")

    op.drop_table("stk_notification")
