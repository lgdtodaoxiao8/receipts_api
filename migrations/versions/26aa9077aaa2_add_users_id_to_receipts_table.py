"""add user_id to receipts table

Revision ID: 26aa9077aaa2
Revises: 3d5e9c13787d
Create Date: 2026-10-23 13:33:35.413129

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "26aa9077aaa2"
down_revision: str | Sequence[str] | None = "3d5e9c13787d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # до авторизации чеки были тестовыми без владельца, поэтому их можно удалить
    # кейс nullable > fill > not null тут лишний
    op.execute("TRUNCATE receipts RESTART IDENTITY CASCADE")
    op.add_column("receipts", sa.Column("user_id", sa.Integer(), nullable=False))

    op.create_foreign_key(
        "fk_receipts_users",
        "receipts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index("idx_receipts_user_id", "receipts", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("fk_receipts_users", "receipts", type_="foreignkey")

    op.drop_index("idx_receipts_user_id", "receipts")

    op.drop_column("receipts", "user_id")
