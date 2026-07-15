"""store estimated Qarina provider usage"""

import sqlalchemy as sa

from alembic import op

revision = "20260715_0002"
down_revision = "20260715_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_run", sa.Column("costs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("research_run", "costs")
