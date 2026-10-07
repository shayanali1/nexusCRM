"""Initial schema for NexusCRM core multi-tenant architecture

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Organizations
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), unique=True, nullable=False),
        sa.Column('domain', sa.String(255), nullable=True),
        sa.Column('logo_url', sa.String(1024), nullable=True),
        sa.Column('plan', sa.String(50), server_default='starter', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('settings', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_organizations_slug', 'organizations', ['slug'], unique=True)

    # 2. Users
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('role', sa.String(50), server_default='MEMBER', nullable=False),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('avatar_url', sa.String(1024), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_org_id', 'users', ['organization_id'])
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_org_email', 'users', ['organization_id', 'email'], unique=True)

    # 3. Roles
    op.create_table(
        'roles',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('permissions', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_roles_org_id', 'roles', ['organization_id'])

    # 4. Companies
    op.create_table(
        'companies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=True),
        sa.Column('industry', sa.String(100), nullable=True),
        sa.Column('size', sa.String(50), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('website', sa.String(500), nullable=True),
        sa.Column('address', sa.String(500), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('country', sa.String(100), nullable=True),
        sa.Column('custom_fields', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_companies_org_id', 'companies', ['organization_id'])
    op.create_index('ix_companies_org_name', 'companies', ['organization_id', 'name'])

    # 5. Contacts
    op.create_table(
        'contacts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('title', sa.String(150), nullable=True),
        sa.Column('lead_source', sa.String(100), nullable=True),
        sa.Column('address', sa.String(500), nullable=True),
        sa.Column('custom_fields', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_contacts_org_id', 'contacts', ['organization_id'])
    op.create_index('ix_contacts_company_id', 'contacts', ['company_id'])
    op.create_index('ix_contacts_org_email', 'contacts', ['organization_id', 'email'])

    # 6. Pipelines
    op.create_table(
        'pipelines',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_pipelines_org_id', 'pipelines', ['organization_id'])
    op.create_index('ix_pipelines_org_default', 'pipelines', ['organization_id', 'is_default'])

    # 7. Pipeline Stages
    op.create_table(
        'pipeline_stages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('pipeline_id', sa.String(36), sa.ForeignKey('pipelines.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('order', sa.Integer(), server_default='1', nullable=False),
        sa.Column('win_probability', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_won', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_lost', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_pipeline_stages_org_id', 'pipeline_stages', ['organization_id'])
    op.create_index('ix_pipeline_stages_pipeline_id', 'pipeline_stages', ['pipeline_id'])
    op.create_index('ix_pipeline_stages_pipeline_order', 'pipeline_stages', ['pipeline_id', 'order'])

    # 8. Deals
    op.create_table(
        'deals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('pipeline_id', sa.String(36), sa.ForeignKey('pipelines.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('stage_id', sa.String(36), sa.ForeignKey('pipeline_stages.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assigned_to_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('value', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('currency', sa.String(10), server_default='USD', nullable=False),
        sa.Column('status', sa.String(50), server_default='OPEN', nullable=False),
        sa.Column('win_probability', sa.Integer(), server_default='50', nullable=False),
        sa.Column('expected_close_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lost_reason', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('custom_fields', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_deals_org_id', 'deals', ['organization_id'])
    op.create_index('ix_deals_org_status', 'deals', ['organization_id', 'status'])
    op.create_index('ix_deals_org_stage', 'deals', ['organization_id', 'stage_id'])

    # 9. Leads
    op.create_table(
        'leads',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assigned_to_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), server_default='NEW', nullable=False),
        sa.Column('source', sa.String(100), server_default='Website', nullable=False),
        sa.Column('score', sa.Integer(), server_default='50', nullable=False),
        sa.Column('priority', sa.String(50), server_default='MEDIUM', nullable=False),
        sa.Column('estimated_value', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('currency', sa.String(10), server_default='USD', nullable=False),
        sa.Column('lost_reason', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('custom_fields', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('converted_to_deal_id', sa.String(36), sa.ForeignKey('deals.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_leads_org_id', 'leads', ['organization_id'])
    op.create_index('ix_leads_org_status', 'leads', ['organization_id', 'status'])
    op.create_index('ix_leads_org_priority', 'leads', ['organization_id', 'priority'])

    # 10. Activities
    op.create_table(
        'activities',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('lead_id', sa.String(36), sa.ForeignKey('leads.id', ondelete='CASCADE'), nullable=True),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('deal_id', sa.String(36), sa.ForeignKey('deals.id', ondelete='CASCADE'), nullable=True),
        sa.Column('activity_type', sa.String(50), server_default='NOTE', nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('outcome', sa.String(100), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), server_default='0', nullable=False),
        sa.Column('performed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('extra_metadata', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_activities_org_id', 'activities', ['organization_id'])
    op.create_index('ix_activities_org_performed', 'activities', ['organization_id', 'performed_at'])

    # 11. Tasks
    op.create_table(
        'tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assigned_to_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_by_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('lead_id', sa.String(36), sa.ForeignKey('leads.id', ondelete='CASCADE'), nullable=True),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('deal_id', sa.String(36), sa.ForeignKey('deals.id', ondelete='CASCADE'), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('task_type', sa.String(50), server_default='FOLLOW_UP', nullable=False),
        sa.Column('priority', sa.String(50), server_default='MEDIUM', nullable=False),
        sa.Column('status', sa.String(50), server_default='PENDING', nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_tasks_org_id', 'tasks', ['organization_id'])
    op.create_index('ix_tasks_org_due', 'tasks', ['organization_id', 'due_date'])
    op.create_index('ix_tasks_org_status', 'tasks', ['organization_id', 'status'])

    # 12. Calendar Events
    op.create_table(
        'calendar_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('lead_id', sa.String(36), sa.ForeignKey('leads.id', ondelete='CASCADE'), nullable=True),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('deal_id', sa.String(36), sa.ForeignKey('deals.id', ondelete='CASCADE'), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('meeting_link', sa.String(500), nullable=True),
        sa.Column('external_event_id', sa.String(255), nullable=True),
        sa.Column('provider', sa.String(50), server_default='google', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_calendar_events_org_id', 'calendar_events', ['organization_id'])

    # 13. Automation Rules & Actions
    op.create_table(
        'automation_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('event_trigger', sa.String(100), nullable=False),
        sa.Column('conditions', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_automation_rules_org_id', 'automation_rules', ['organization_id'])

    op.create_table(
        'automation_actions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('rule_id', sa.String(36), sa.ForeignKey('automation_rules.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action_type', sa.String(100), nullable=False),
        sa.Column('action_config', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('execution_order', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_automation_actions_rule_id', 'automation_actions', ['rule_id'])

    # 14. AI Insights & Jobs
    op.create_table(
        'ai_insights',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(36), nullable=False),
        sa.Column('insight_type', sa.String(50), nullable=False),
        sa.Column('content', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('confidence', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('model_name', sa.String(100), server_default='mock-ai-engine', nullable=False),
        sa.Column('provider_name', sa.String(50), server_default='mock', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_ai_insights_lookup', 'ai_insights', ['organization_id', 'entity_type', 'entity_id', 'insight_type'])

    op.create_table(
        'ai_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_type', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), server_default='PENDING', nullable=False),
        sa.Column('payload', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 15. Notifications
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('notification_type', sa.String(50), server_default='INFO', nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('link', sa.String(500), nullable=True),
        sa.Column('extra_metadata', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_notifications_user_read', 'notifications', ['user_id', 'is_read'])

    # 16. Import Jobs & Rows
    op.create_table(
        'import_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(1024), nullable=False),
        sa.Column('status', sa.String(50), server_default='PENDING', nullable=False),
        sa.Column('total_rows', sa.Integer(), server_default='0', nullable=False),
        sa.Column('processed_rows', sa.Integer(), server_default='0', nullable=False),
        sa.Column('successful_rows', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed_rows', sa.Integer(), server_default='0', nullable=False),
        sa.Column('errors', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'import_rows',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('import_job_id', sa.String(36), sa.ForeignKey('import_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('raw_data', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('status', sa.String(50), server_default='PENDING', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 17. Integrations & Audit Logs
    op.create_table(
        'integrations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(100), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('config', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('credentials', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_integrations_org_provider', 'integrations', ['organization_id', 'provider'], unique=True)

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', sa.String(36), nullable=True),
        sa.Column('changes', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_audit_logs_org_created', 'audit_logs', ['organization_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('integrations')
    op.drop_table('import_rows')
    op.drop_table('import_jobs')
    op.drop_table('notifications')
    op.drop_table('ai_jobs')
    op.drop_table('ai_insights')
    op.drop_table('automation_actions')
    op.drop_table('automation_rules')
    op.drop_table('calendar_events')
    op.drop_table('tasks')
    op.drop_table('activities')
    op.drop_table('leads')
    op.drop_table('deals')
    op.drop_table('pipeline_stages')
    op.drop_table('pipelines')
    op.drop_table('contacts')
    op.drop_table('companies')
    op.drop_table('roles')
    op.drop_table('users')
    op.drop_table('organizations')
