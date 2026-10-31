"""stk files: one row per upload, bytes content-addressed on disk."""

import sqlalchemy as sa
from alembic import op

revision = "stk_0003"
down_revision = "stk_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stk_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("thumb_sha256", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_stk_file_user_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stk_file")),
    )
    with op.batch_alter_table("stk_file", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stk_file_sha256"), ["sha256"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_stk_file_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("stk_file", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stk_file_user_id"))
        batch_op.drop_index(batch_op.f("ix_stk_file_sha256"))

    op.drop_table("stk_file")
