"""Phase 2 workflow columns: extra_metadata in tasks, duplicate_rows in import_jobs

Revision ID: 002_phase2_workflows
Revises: 001_initial_schema
Create Date: 2026-10-09 17:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_phase2_workflows'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('extra_metadata', sa.JSON(), server_default='{}', nullable=False))
    op.add_column('import_jobs', sa.Column('duplicate_rows', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('import_jobs', 'duplicate_rows')
    op.drop_column('tasks', 'extra_metadata')
