"""Mark every existing account confirmed.

stk 17.3 turns on email confirmation, and an account with no `confirmed_at` can
no longer sign in. No account before this revision ever had to confirm, so all
of them count as confirmed; only sign-ups from now on wait for the email.
"""

import sqlalchemy as sa
from alembic import op

revision = "stk_0007"
down_revision = "stk_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    user = sa.table("user", sa.column("confirmed_at", sa.DateTime()))
    op.execute(
        user.update()
        .where(user.c.confirmed_at.is_(None))
        .values(confirmed_at=sa.func.current_timestamp())
    )


def downgrade() -> None:
    # Which accounts were unconfirmed before is not recorded; leave them all.
    pass
