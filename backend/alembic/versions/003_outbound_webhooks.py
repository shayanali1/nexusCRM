"""Phase 5 Step 6.3.1: Outbound webhook subscriptions and deliveries

Revision ID: 003_outbound_webhooks
Revises: 002_phase2_workflows
Create Date: 2026-10-21 15:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003_outbound_webhooks'
down_revision: Union[str, None] = '002_phase2_workflows'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Webhook Subscriptions
    op.create_table(
        'webhook_subscriptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('events', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('secret', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('consecutive_failures', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('id', 'organization_id', name='uq_webhook_subscriptions_id_org'),
    )
    op.create_index('ix_webhook_subscriptions_organization_id', 'webhook_subscriptions', ['organization_id'])
    op.create_index('ix_webhook_subscriptions_org_active', 'webhook_subscriptions', ['organization_id', 'is_active'])
    op.create_index('ix_webhook_subscriptions_org_name', 'webhook_subscriptions', ['organization_id', 'name'])

    # 2. Webhook Deliveries
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subscription_id', sa.String(36), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('event_id', sa.String(100), nullable=False),
        sa.Column('payload', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('response_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('execution_time_ms', sa.Float(), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['subscription_id', 'organization_id'],
            ['webhook_subscriptions.id', 'webhook_subscriptions.organization_id'],
            ondelete='CASCADE',
            name='fk_webhook_deliveries_subscription_org',
        ),
        sa.UniqueConstraint('subscription_id', 'event_id', name='uq_webhook_deliveries_sub_event'),
    )
    op.create_index('ix_webhook_deliveries_organization_id', 'webhook_deliveries', ['organization_id'])
    op.create_index('ix_webhook_deliveries_event_type', 'webhook_deliveries', ['event_type'])
    op.create_index('ix_webhook_deliveries_event_id', 'webhook_deliveries', ['event_id'])
    op.create_index('ix_webhook_deliveries_status', 'webhook_deliveries', ['status'])
    op.create_index('ix_webhook_deliveries_org_status', 'webhook_deliveries', ['organization_id', 'status'])
    op.create_index('ix_webhook_deliveries_org_created', 'webhook_deliveries', ['organization_id', 'created_at'])
    op.create_index('ix_webhook_deliveries_sub_created', 'webhook_deliveries', ['subscription_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('webhook_deliveries')
    op.drop_table('webhook_subscriptions')
