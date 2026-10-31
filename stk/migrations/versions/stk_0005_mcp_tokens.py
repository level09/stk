"""MCP bearer tokens: one row per token, storing only its sha256.

Until 17.2.3 this created `mcp_token`, a name an app may already use for its own
table; stk_0006 moves such an stk table to `stk_mcp_token`."""

import sqlalchemy as sa
from alembic import op

revision = "stk_0005"
down_revision = "stk_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stk_mcp_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_uniquifier", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_stk_mcp_token_user_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stk_mcp_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_stk_mcp_token_token_hash")),
    )
    with op.batch_alter_table("stk_mcp_token", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stk_mcp_token_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("stk_mcp_token", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stk_mcp_token_user_id"))
    op.drop_table("stk_mcp_token")
