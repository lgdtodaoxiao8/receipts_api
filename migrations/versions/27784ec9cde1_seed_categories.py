"""seed categories

Revision ID: 27784ec9cde1
Revises: c3dedc88c41c
Create Date: 2026-09-28 15:19:20.757075

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "27784ec9cde1"
down_revision: str | Sequence[str] | None = "c3dedc88c41c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CATEGORIES = [
    "Молочные продукты",
    "Хлеб и выпечка",
    "Мясо и рыба",
    "Овощи и фрукты",
    "Бакалея и крупы",
    "Замороженные продукты",
    "Напитки",
    "Алкоголь и табак",
    "Сладости и снеки",
    "Готовая еда",
    "Бытовая химия",
    "Гигиена и косметика",
    "Товары для дома",
    "Детские товары",
    "Товары для животных",
    "Аптека",
]


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("INSERT INTO categories (name) VALUES (:name) ON CONFLICT DO NOTHING"),
        [{"name": name} for name in CATEGORIES],
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM categories WHERE name = :name"),
        [{"name": name} for name in CATEGORIES],
    )
