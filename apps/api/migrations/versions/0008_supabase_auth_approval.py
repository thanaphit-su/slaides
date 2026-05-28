"""add supabase auth link and approval state

Revision ID: 0008_supabase_auth_approval
Revises: 0007_session_slide_theme_default
Create Date: 2026-05-21

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_supabase_auth_approval"
down_revision = "0007_session_slide_theme_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    uuid_type = postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)

    with op.batch_alter_table("app_user") as batch:
        batch.add_column(sa.Column("supabase_user_id", uuid_type, nullable=True))
        batch.add_column(
            sa.Column(
                "approval_status",
                sa.String(length=40),
                nullable=False,
                server_default="approved",
            )
        )
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint("uq_app_user_supabase_user_id", ["supabase_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("app_user") as batch:
        batch.drop_constraint("uq_app_user_supabase_user_id", type_="unique")
        batch.drop_column("approved_at")
        batch.drop_column("approval_status")
        batch.drop_column("supabase_user_id")
