"""index receipts purchased_at

Revision ID: 1bf080b8322f
Revises: 27784ec9cde1
Create Date: 2026-10-03 21:37:36.129927

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1bf080b8322f"
down_revision: str | Sequence[str] | None = "27784ec9cde1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE INDEX idx_receipts_purchased_at ON receipts(purchased_at)")


def downgrade() -> None:
    op.execute("DROP INDEX idx_receipts_purchased_at")
