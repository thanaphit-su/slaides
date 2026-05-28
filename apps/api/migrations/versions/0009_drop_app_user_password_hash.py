"""drop app_user.password_hash

The pre-Supabase argon2 instructor auth path was removed in the security
pass. The column has been permanently empty since; no code reads it.

Revision ID: 0009_drop_app_user_password_hash
Revises: 0008_supabase_auth_approval
Create Date: 2026-05-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_drop_app_user_password_hash"
down_revision = "0008_supabase_auth_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("app_user") as batch:
        batch.drop_column("password_hash")


def downgrade() -> None:
    with op.batch_alter_table("app_user") as batch:
        batch.add_column(
            sa.Column(
                "password_hash",
                sa.String(length=500),
                nullable=False,
                server_default="",
            )
        )
