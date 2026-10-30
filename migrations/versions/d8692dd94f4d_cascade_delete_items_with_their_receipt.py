"""cascade delete items with their receipt

Revision ID: d8692dd94f4d
Revises: 26aa9077aaa2
Create Date: 2026-10-30 15:01:08.845481

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8692dd94f4d"
down_revision: str | Sequence[str] | None = "26aa9077aaa2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("items_receipt_id_fkey", "items", type_="foreignkey")
    op.create_foreign_key(
        "items_receipt_id_fkey",
        "items",
        "receipts",
        ["receipt_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("items_receipt_id_fkey", "items", type_="foreignkey")
    op.create_foreign_key(
        "items_receipt_id_fkey",
        "items",
        "receipts",
        ["receipt_id"],
        ["id"],
    )
