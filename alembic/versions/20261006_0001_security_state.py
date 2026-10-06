"""Add shared authentication state for quart-security 2."""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0001"
down_revision = "228ac4e0ebf5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quart_security_state",
        sa.Column("token", sa.String(160), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_quart_security_state_expires_at", "quart_security_state", ["expires_at"]
    )


def downgrade():
    op.drop_index("ix_quart_security_state_expires_at", "quart_security_state")
    op.drop_table("quart_security_state")
