"""add table refresh_tokens

Revision ID: 399c026bd8fb
Revises: d8692dd94f4d
Create Date: 2026-11-06 14:37:13.281674

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "399c026bd8fb"
down_revision: str | Sequence[str] | None = "d8692dd94f4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE refresh_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL
        )
    """
    )


def downgrade() -> None:

    op.execute("DROP TABLE refresh_tokens")
