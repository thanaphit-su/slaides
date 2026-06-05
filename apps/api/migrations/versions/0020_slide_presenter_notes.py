"""Add slide presenter notes.

Revision ID: 0020_slide_presenter_notes
Revises: 0019_llm_interpret_cache
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0020_slide_presenter_notes"
down_revision = "0019_llm_interpret_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("slide") as batch:
        batch.add_column(sa.Column("presenter_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("slide") as batch:
        batch.drop_column("presenter_notes")
