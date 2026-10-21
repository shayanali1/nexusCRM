"""Tests for outbound webhook models and database constraints (Phase 5 Step 6.3.1).

Covers:
- WebhookSubscription and WebhookDelivery instantiation, defaults, and JSON fields
- Multiple subscriptions per organization
- Bidirectional ORM relationships between Organization, WebhookSubscription, and WebhookDelivery
- Cascade deletion of deliveries on subscription or organization deletion
- Database-level duplicate prevention for (subscription_id, event_id)
- Database-level cross-tenant foreign key rejection
- Alembic migration 003_outbound_webhooks validity
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.modules.organizations.models import Organization
from app.modules.integrations.models import WebhookSubscription, WebhookDelivery


@pytest.mark.asyncio
async def test_webhook_subscription_model_creation(db_session: AsyncSession, test_org: Organization):
    """Test WebhookSubscription model creation, defaults, and field persistence."""
    sub = WebhookSubscription(
        organization_id=test_org.id,
        name="Zapier Lead Sync",
        url="https://hooks.zapier.com/catch/123/abc",
        events=["lead.created", "deal.won"],
        secret={"encrypted_value": "enc_payload", "key_id": "k1"},
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.id is not None
    assert len(sub.id) == 36
    assert sub.name == "Zapier Lead Sync"
    assert sub.url == "https://hooks.zapier.com/catch/123/abc"
    assert sub.events == ["lead.created", "deal.won"]
    assert sub.secret == {"encrypted_value": "enc_payload", "key_id": "k1"}
    assert sub.is_active is True
    assert sub.consecutive_failures == 0
    assert sub.created_at is not None
    assert sub.updated_at is not None


@pytest.mark.asyncio
async def test_multiple_subscriptions_per_organization(db_session: AsyncSession, test_org: Organization):
    """Test that multiple webhook subscriptions can be created for the same organization."""
    sub1 = WebhookSubscription(
        organization_id=test_org.id,
        name="Slack Deal Alerts",
        url="https://hooks.slack.com/services/T00/B00/X00",
        events=["deal.won", "deal.lost"],
        secret={"encrypted_value": "enc_1"},
    )
    sub2 = WebhookSubscription(
        organization_id=test_org.id,
        name="Customer Portal Sync",
        url="https://api.example.com/webhooks/crm",
        events=["contact.created", "contact.updated"],
        secret={"encrypted_value": "enc_2"},
    )
    sub3 = WebhookSubscription(
        organization_id=test_org.id,
        name="ERP Integration",
        url="https://erp.example.com/events",
        events=["deal.won"],
        secret={"encrypted_value": "enc_3"},
    )
    db_session.add_all([sub1, sub2, sub3])
    await db_session.commit()

    result = await db_session.execute(
        select(WebhookSubscription).where(WebhookSubscription.organization_id == test_org.id)
    )
    subs = result.scalars().all()
    assert len(subs) == 3
    names = {s.name for s in subs}
    assert names == {"Slack Deal Alerts", "Customer Portal Sync", "ERP Integration"}


@pytest.mark.asyncio
async def test_webhook_delivery_model_creation_and_defaults(
    db_session: AsyncSession, test_org: Organization
):
    """Test WebhookDelivery creation, default values, and operational metrics fields."""
    sub = WebhookSubscription(
        organization_id=test_org.id,
        name="Billing Event Bus",
        url="https://billing.example.com/webhook",
        events=["deal.won"],
        secret={"ciphertext": "secret123"},
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    now = datetime.now(timezone.utc)
    delivery = WebhookDelivery(
        organization_id=test_org.id,
        subscription_id=sub.id,
        event_type="deal.won",
        event_id="evt_deal_998877",
        payload={"deal_id": "d-123", "amount": 50000.0, "currency": "USD"},
        status="success",
        attempt_count=1,
        response_status_code=200,
        response_body='{"received": true}',
        error_message=None,
        execution_time_ms=124.5,
        last_attempt_at=now,
        delivered_at=now,
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    assert delivery.id is not None
    assert delivery.subscription_id == sub.id
    assert delivery.organization_id == test_org.id
    assert delivery.event_type == "deal.won"
    assert delivery.event_id == "evt_deal_998877"
    assert delivery.payload["deal_id"] == "d-123"
    assert delivery.status == "success"
    assert delivery.attempt_count == 1
    assert delivery.response_status_code == 200
    assert delivery.response_body == '{"received": true}'
    assert delivery.execution_time_ms == 124.5
    assert delivery.delivered_at is not None


@pytest.mark.asyncio
async def test_bidirectional_relationships(db_session: AsyncSession, test_org: Organization):
    """Test bidirectional ORM relationships between Organization, WebhookSubscription, and WebhookDelivery."""
    from sqlalchemy.orm import selectinload

    sub = WebhookSubscription(
        organization_id=test_org.id,
        name="Audit Mirror",
        url="https://mirror.example.com/audit",
        events=["audit.created"],
        secret={"key": "val"},
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    delivery = WebhookDelivery(
        organization_id=test_org.id,
        subscription_id=sub.id,
        event_type="audit.created",
        event_id="evt_audit_001",
        payload={"action": "user.login"},
    )
    db_session.add(delivery)
    await db_session.commit()
    await db_session.refresh(delivery)

    # 1. Organization -> WebhookSubscriptions & WebhookDeliveries
    query = await db_session.execute(
        select(Organization)
        .options(
            selectinload(Organization.webhook_subscriptions),
            selectinload(Organization.webhook_deliveries),
        )
        .where(Organization.id == test_org.id)
    )
    org_loaded = query.scalar_one()
    sub_ids = [s.id for s in org_loaded.webhook_subscriptions]
    deliv_ids = [d.id for d in org_loaded.webhook_deliveries]
    assert sub.id in sub_ids
    assert delivery.id in deliv_ids

    # 2. WebhookSubscription -> Organization & WebhookDeliveries
    sub_query = await db_session.execute(
        select(WebhookSubscription)
        .options(
            selectinload(WebhookSubscription.organization),
            selectinload(WebhookSubscription.deliveries),
        )
        .where(WebhookSubscription.id == sub.id)
    )
    sub_loaded = sub_query.scalar_one()
    assert sub_loaded.organization.id == test_org.id
    assert delivery.id in [d.id for d in sub_loaded.deliveries]

    # 3. WebhookDelivery -> WebhookSubscription & Organization
    deliv_query = await db_session.execute(
        select(WebhookDelivery)
        .options(
            selectinload(WebhookDelivery.subscription),
            selectinload(WebhookDelivery.organization),
        )
        .where(WebhookDelivery.id == delivery.id)
    )
    deliv_loaded = deliv_query.scalar_one()
    assert deliv_loaded.subscription.id == sub.id
    assert deliv_loaded.organization.id == test_org.id



@pytest.mark.asyncio
async def test_cascade_delete_subscription_deletes_deliveries(
    db_session: AsyncSession, test_org: Organization
):
    """Deleting a subscription must cascade delete its deliveries."""
    sub = WebhookSubscription(
        organization_id=test_org.id,
        name="Temporary Sub",
        url="https://temp.example.com/events",
        events=["lead.created"],
        secret={"data": "sec"},
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    sub_id = sub.id

    deliv1 = WebhookDelivery(
        organization_id=test_org.id,
        subscription_id=sub.id,
        event_type="lead.created",
        event_id="evt_lead_1",
        payload={"lead": 1},
    )
    deliv2 = WebhookDelivery(
        organization_id=test_org.id,
        subscription_id=sub.id,
        event_type="lead.created",
        event_id="evt_lead_2",
        payload={"lead": 2},
    )
    db_session.add_all([deliv1, deliv2])
    await db_session.commit()

    # Delete subscription
    await db_session.delete(sub)
    await db_session.commit()

    # Verify deliveries are gone
    remaining_delivs = await db_session.execute(
        select(WebhookDelivery).where(WebhookDelivery.subscription_id == sub_id)
    )
    assert len(remaining_delivs.scalars().all()) == 0


@pytest.mark.asyncio
async def test_cascade_delete_organization_deletes_subscriptions_and_deliveries(
    db_session: AsyncSession
):
    """Deleting an organization must cascade delete all its subscriptions and deliveries."""
    org = Organization(name="Org To Delete", slug="org-to-delete", is_active=True)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    org_id = org.id

    sub = WebhookSubscription(
        organization_id=org_id,
        name="Cascade Sub",
        url="https://cascade.example.com",
        events=["deal.created"],
        secret={},
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    sub_id = sub.id

    deliv = WebhookDelivery(
        organization_id=org_id,
        subscription_id=sub_id,
        event_type="deal.created",
        event_id="evt_deal_cascade_1",
        payload={},
    )
    db_session.add(deliv)
    await db_session.commit()

    # Delete organization
    await db_session.delete(org)
    await db_session.commit()

    # Verify subscriptions and deliveries are gone
    remaining_subs = await db_session.execute(
        select(WebhookSubscription).where(WebhookSubscription.organization_id == org_id)
    )
    assert len(remaining_subs.scalars().all()) == 0

    remaining_delivs = await db_session.execute(
        select(WebhookDelivery).where(WebhookDelivery.organization_id == org_id)
    )
    assert len(remaining_delivs.scalars().all()) == 0


@pytest.mark.asyncio
async def test_duplicate_delivery_prevention(db_session: AsyncSession, test_org: Organization):
    """Database-level unique constraint prevents duplicate deliveries for the same subscription and event_id."""
    sub = WebhookSubscription(
        organization_id=test_org.id,
        name="Deduplication Target",
        url="https://example.com/dedup",
        events=["contact.created"],
        secret={},
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    deliv1 = WebhookDelivery(
        organization_id=test_org.id,
        subscription_id=sub.id,
        event_type="contact.created",
        event_id="evt_unique_100",
        payload={"contact_id": "c1"},
    )
    db_session.add(deliv1)
    await db_session.commit()

    # Second delivery with the same subscription_id and event_id must violate unique constraint
    deliv2 = WebhookDelivery(
        organization_id=test_org.id,
        subscription_id=sub.id,
        event_type="contact.created",
        event_id="evt_unique_100",
        payload={"contact_id": "c1", "retry": True},
    )
    db_session.add(deliv2)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_cross_tenant_foreign_key_rejection(db_session: AsyncSession, test_org: Organization):
    """A delivery cannot reference a subscription belonging to another tenant organization."""
    # Enable SQLite foreign key constraint checks if running SQLite
    await db_session.execute(text("PRAGMA foreign_keys=ON"))

    # Create Organization Beta
    org_b = Organization(name="Org Beta Webhooks", slug="org-beta-webhooks", is_active=True)
    db_session.add(org_b)
    await db_session.commit()
    await db_session.refresh(org_b)

    org_a_id = test_org.id
    org_b_id = org_b.id

    # Create subscription belonging to Org A
    sub_a = WebhookSubscription(
        organization_id=org_a_id,
        name="Org A Secret Sub",
        url="https://org-a.com/webhook",
        events=["deal.won"],
        secret={},
    )
    db_session.add(sub_a)
    await db_session.commit()
    await db_session.refresh(sub_a)
    sub_a_id = sub_a.id

    # Attempt to insert a delivery belonging to Org B that references Org A's subscription
    invalid_delivery = WebhookDelivery(
        organization_id=org_b_id,
        subscription_id=sub_a_id,
        event_type="deal.won",
        event_id="evt_cross_tenant_999",
        payload={"deal": "stolen"},
    )
    db_session.add(invalid_delivery)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_alembic_migration_003_metadata():
    """Verify Alembic migration 003 revision chain and metadata."""
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = str(backend_dir / "alembic.ini")
    script_loc = str(backend_dir / "alembic")
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("script_location", script_loc)
    script_dir = ScriptDirectory.from_config(alembic_cfg)

    head_rev = script_dir.get_current_head()
    assert head_rev == "003_outbound_webhooks"

    rev_003 = script_dir.get_revision("003_outbound_webhooks")
    assert rev_003 is not None
    assert rev_003.down_revision == "002_phase2_workflows"

