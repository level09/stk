"""Move stk's MCP tokens from `mcp_token` to `stk_mcp_token`.

stk 17.2.0 to 17.2.2 created `mcp_token`, a name an app may already use for its
own table. stk_0005 now creates `stk_mcp_token`; a database that ran the old
stk_0005 has stk's tokens in `mcp_token` instead. Only that table moves: it is
recognised by stk's `user_uniquifier` column, so an app's own `mcp_token` stays.
"""

import sqlalchemy as sa
from alembic import op

revision = "stk_0006"
down_revision = "stk_0005"
branch_labels = None
depends_on = None

COLUMNS = (
    "id, user_id, name, token_hash, user_uniquifier, scopes, created_at,"
    " expires_at, last_used_at"
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "mcp_token" not in tables:
        return
    legacy = {c["name"] for c in inspector.get_columns("mcp_token")}
    if "user_uniquifier" not in legacy or "token_hash" not in legacy:
        return
    if "stk_mcp_token" not in tables:
        # The database ran the old stk_0005, so the new one never created this.
        _create_stk_mcp_token()
    op.execute(f"INSERT INTO stk_mcp_token ({COLUMNS}) SELECT {COLUMNS} FROM mcp_token")
    # destructive: every row was copied to stk_mcp_token on the line above.
    op.drop_table("mcp_token")


def _create_stk_mcp_token():
    # Same table as stk_0005 creates; revision modules cannot import each other.
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
    # The old name collided with apps' own tables; there is nothing to restore.
    pass
