"""initial schema

Revision ID: c3dedc88c41c
Revises:
Create Date: 2026-09-25 21:20:52.980561

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3dedc88c41c"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE receipts (
            id SERIAL PRIMARY KEY,
            purchased_at TIMESTAMPTZ NOT NULL,
            total NUMERIC(10,2) CHECK (total >= 0),
            shop TEXT
        )
    """)

    op.execute("""
        CREATE TABLE categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
    """)

    op.execute("""
        CREATE TABLE items (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL CHECK (length(trim(name)) > 0),
            price NUMERIC(10,2) NOT NULL CHECK (price > 0),
            receipt_id INTEGER NOT NULL REFERENCES receipts(id),
            category_id INTEGER REFERENCES categories(id)
        )
    """)

    op.execute("CREATE INDEX idx_items_receipt_id ON items (receipt_id)")
    op.execute("CREATE INDEX idx_items_category_id ON items (category_id)")


def downgrade() -> None:
    op.execute("DROP TABLE items")
    op.execute("DROP TABLE categories")
    op.execute("DROP TABLE receipts")
