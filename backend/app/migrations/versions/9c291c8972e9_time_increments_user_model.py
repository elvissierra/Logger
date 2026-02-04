"""time increments user model

Revision ID: 9c291c8972e9
Revises: 1e0bd381894e
Create Date: 2026-02-04 14:58:45.855788+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c291c8972e9'
down_revision: Union[str, Sequence[str], None] = '1e0bd381894e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "time_increment_minutes",
            sa.Integer(),
            server_default=sa.text("15"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "users_time_increment_minutes_chk",
        "users",
        "time_increment_minutes IN (1,5,10,15)",
    )
    # Optional: remove server default after backfill so inserts must be explicit
    op.alter_column("users", "time_increment_minutes", server_default=None)


def downgrade() -> None:
    op.drop_constraint("users_time_increment_minutes_chk", "users", type_="check")
    op.drop_column("users", "time_increment_minutes")
