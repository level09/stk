"""Add atomic authentication rate limit windows."""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0002"
down_revision = "20261006_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rate_limit_window",
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_rate_limit_window_expires_at", "rate_limit_window", ["expires_at"]
    )


def downgrade():
    op.drop_index("ix_rate_limit_window_expires_at", "rate_limit_window")
    op.drop_table("rate_limit_window")
