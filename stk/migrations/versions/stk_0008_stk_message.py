"""stk messages: socket pushes routed through the database to every process."""

import sqlalchemy as sa
from alembic import op

revision = "stk_0008"
down_revision = "stk_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stk_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_stk_message_user_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stk_message")),
    )
    with op.batch_alter_table("stk_message", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stk_message_created_at"), ["created_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("stk_message", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stk_message_created_at"))

    op.drop_table("stk_message")
