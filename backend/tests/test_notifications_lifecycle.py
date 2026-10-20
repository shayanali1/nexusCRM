import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password
from app.modules.notifications.models import Notification
from app.modules.organizations.models import Organization
from app.modules.users.models import User


@pytest_asyncio.fixture(scope="function")
async def seed_notifications_data(
    db_session: AsyncSession,
    test_org: Organization,
    test_user_owner: User,
    test_user_member: User,
):
    """Seed comprehensive notification test data across users and organizations."""
    base_time = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Org B (different tenant)
    org_b = Organization(name="Tenant Beta", slug="tenant-beta", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    user_b = User(
        organization_id=org_b.id,
        email="owner@tenantbeta.com",
        hashed_password=hash_password("password123"),
        first_name="Beta",
        last_name="Owner",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    # User Owner (Org A) notifications:
    # n1: unread, LEAD_ASSIGNED, 3h ago
    n1 = Notification(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        title="Lead Assigned: MegaCorp",
        message="A new lead has been assigned to you.",
        notification_type="LEAD_ASSIGNED",
        is_read=False,
        created_at=base_time - timedelta(hours=3),
    )
    # n2: unread, TASK_DUE, 2h ago
    n2 = Notification(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        title="Task Due: Follow Up Call",
        message="Your scheduled follow-up is due soon.",
        notification_type="TASK_DUE",
        is_read=False,
        created_at=base_time - timedelta(hours=2),
    )
    # n3: read, DEAL_WON, 1h ago
    n3 = Notification(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        title="Deal Won: Enterprise Expansion",
        message="Congratulations! Deal closed as WON.",
        notification_type="DEAL_WON",
        is_read=True,
        read_at=base_time - timedelta(minutes=30),
        created_at=base_time - timedelta(hours=1),
    )
    # n4: unread, AI_INSIGHT, now
    n4 = Notification(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        title="AI Insight Generated",
        message="Executive briefing has been processed.",
        notification_type="AI_INSIGHT",
        is_read=False,
        created_at=base_time,
    )
    db_session.add_all([n1, n2, n3, n4])

    # User Member (Org A) notifications:
    nm1 = Notification(
        organization_id=test_org.id,
        user_id=test_user_member.id,
        title="Member Task Due",
        message="Member task requires action.",
        notification_type="TASK_DUE",
        is_read=False,
        created_at=base_time - timedelta(hours=2),
    )
    nm2 = Notification(
        organization_id=test_org.id,
        user_id=test_user_member.id,
        title="Member System Update",
        message="Platform maintenance scheduled.",
        notification_type="INFO",
        is_read=True,
        read_at=base_time - timedelta(minutes=10),
        created_at=base_time - timedelta(hours=1),
    )
    db_session.add_all([nm1, nm2])

    # User Beta (Org B) notifications:
    nb1 = Notification(
        organization_id=org_b.id,
        user_id=user_b.id,
        title="Beta Deal Won",
        message="Confidential Org B notification.",
        notification_type="DEAL_WON",
        is_read=False,
        created_at=base_time,
    )
    db_session.add(nb1)

    await db_session.commit()
    for item in [n1, n2, n3, n4, nm1, nm2, nb1]:
        await db_session.refresh(item)

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)
    auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    return {
        "n1": n1,
        "n2": n2,
        "n3": n3,
        "n4": n4,
        "nm1": nm1,
        "nm2": nm2,
        "nb1": nb1,
        "user_b": user_b,
        "auth_headers_b": auth_headers_b,
    }


# ==============================================================================
# 1. Listing Notifications with Filters, Sorting, and Pagination
# ==============================================================================


@pytest.mark.asyncio
async def test_list_notifications_filtering_and_pagination(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_notifications_data: dict,
):
    """Test listing notifications with default descending sort, unread filter, type filter, and pagination."""
    # 1. Default list (all 4 notifications for owner, sorted desc by created_at)
    res = await client.get("/api/v1/notifications", headers=auth_headers_owner)
    assert res.status_code == 200
    all_notifs = res.json()
    assert len(all_notifs) == 4
    assert [n["title"] for n in all_notifs] == [
        "AI Insight Generated",
        "Deal Won: Enterprise Expansion",
        "Task Due: Follow Up Call",
        "Lead Assigned: MegaCorp",
    ]

    # 2. unread_only=true (filters out read notification n3)
    unread_res = await client.get("/api/v1/notifications?unread_only=true", headers=auth_headers_owner)
    assert unread_res.status_code == 200
    unread_notifs = unread_res.json()
    assert len(unread_notifs) == 3
    assert all(not n["is_read"] for n in unread_notifs)
    assert [n["title"] for n in unread_notifs] == [
        "AI Insight Generated",
        "Task Due: Follow Up Call",
        "Lead Assigned: MegaCorp",
    ]

    # 3. notification_type filter
    type_res = await client.get("/api/v1/notifications?notification_type=TASK_DUE", headers=auth_headers_owner)
    assert type_res.status_code == 200
    task_notifs = type_res.json()
    assert len(task_notifs) == 1
    assert task_notifs[0]["title"] == "Task Due: Follow Up Call"
    assert task_notifs[0]["notification_type"] == "TASK_DUE"

    # Case-insensitive notification_type check
    type_res_lower = await client.get("/api/v1/notifications?notification_type=lead_assigned", headers=auth_headers_owner)
    assert type_res_lower.status_code == 200
    assert len(type_res_lower.json()) == 1
    assert type_res_lower.json()[0]["notification_type"] == "LEAD_ASSIGNED"

    # 4. Pagination: limit=2, offset=0
    p1 = await client.get("/api/v1/notifications?limit=2&offset=0", headers=auth_headers_owner)
    assert p1.status_code == 200
    assert len(p1.json()) == 2
    assert p1.json()[0]["title"] == "AI Insight Generated"
    assert p1.json()[1]["title"] == "Deal Won: Enterprise Expansion"

    # Pagination: limit=2, offset=2
    p2 = await client.get("/api/v1/notifications?limit=2&offset=2", headers=auth_headers_owner)
    assert p2.status_code == 200
    assert len(p2.json()) == 2
    assert p2.json()[0]["title"] == "Task Due: Follow Up Call"
    assert p2.json()[1]["title"] == "Lead Assigned: MegaCorp"


# ==============================================================================
# 2. Unread Count Endpoint
# ==============================================================================


@pytest.mark.asyncio
async def test_unread_count_endpoint(
    client: AsyncClient,
    auth_headers_owner: dict,
    auth_headers_member: dict,
    seed_notifications_data: dict,
):
    """GET /api/v1/notifications/unread-count accurately returns the count of unread items."""
    data = seed_notifications_data

    # Owner has 3 unread
    res_owner = await client.get("/api/v1/notifications/unread-count", headers=auth_headers_owner)
    assert res_owner.status_code == 200
    assert res_owner.json() == {"unread_count": 3}

    # Member has 1 unread
    res_member = await client.get("/api/v1/notifications/unread-count", headers=auth_headers_member)
    assert res_member.status_code == 200
    assert res_member.json() == {"unread_count": 1}

    # Beta user has 1 unread
    res_beta = await client.get("/api/v1/notifications/unread-count", headers=data["auth_headers_b"])
    assert res_beta.status_code == 200
    assert res_beta.json() == {"unread_count": 1}


# ==============================================================================
# 3. Single Notification Read / Unread Toggle
# ==============================================================================


@pytest.mark.asyncio
async def test_patch_notification_read_and_unread(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_notifications_data: dict,
):
    """PATCH /api/v1/notifications/{id}/read marks notification as read/unread and sets read_at timestamp."""
    n1 = seed_notifications_data["n1"]

    # 1. Mark as read with empty body (default is_read=True)
    res = await client.patch(f"/api/v1/notifications/{n1.id}/read", headers=auth_headers_owner)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == n1.id
    assert data["is_read"] is True
    assert data["read_at"] is not None

    # Unread count should decrease from 3 to 2
    count_res = await client.get("/api/v1/notifications/unread-count", headers=auth_headers_owner)
    assert count_res.json()["unread_count"] == 2

    # 2. Mark as unread explicitly with body {"is_read": false}
    res_unread = await client.patch(
        f"/api/v1/notifications/{n1.id}/read",
        json={"is_read": False},
        headers=auth_headers_owner,
    )
    assert res_unread.status_code == 200
    data_unread = res_unread.json()
    assert data_unread["is_read"] is False
    assert data_unread["read_at"] is None

    # Unread count restored to 3
    count_res2 = await client.get("/api/v1/notifications/unread-count", headers=auth_headers_owner)
    assert count_res2.json()["unread_count"] == 3


# ==============================================================================
# 4. Mark All Read Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_mark_all_read_isolation(
    client: AsyncClient,
    auth_headers_owner: dict,
    auth_headers_member: dict,
    seed_notifications_data: dict,
):
    """POST /api/v1/notifications/mark-all-read marks all unread as read for current user only."""
    data = seed_notifications_data

    # Owner marks all read
    res = await client.post("/api/v1/notifications/mark-all-read", headers=auth_headers_owner)
    assert res.status_code == 200
    assert res.json() == {"success": True}

    # Owner unread count is now 0
    res_owner = await client.get("/api/v1/notifications/unread-count", headers=auth_headers_owner)
    assert res_owner.json()["unread_count"] == 0

    # Member's unread notification was untouched
    res_member = await client.get("/api/v1/notifications/unread-count", headers=auth_headers_member)
    assert res_member.json()["unread_count"] == 1

    # Beta's unread notification was untouched
    res_beta = await client.get("/api/v1/notifications/unread-count", headers=data["auth_headers_b"])
    assert res_beta.json()["unread_count"] == 1


# ==============================================================================
# 5. Delete / Dismiss Notification
# ==============================================================================


@pytest.mark.asyncio
async def test_delete_notification(
    client: AsyncClient,
    auth_headers_member: dict,
    seed_notifications_data: dict,
):
    """DELETE /api/v1/notifications/{id} removes the notification and updates unread count."""
    nm1 = seed_notifications_data["nm1"]

    # Member has 1 unread
    cnt_before = await client.get("/api/v1/notifications/unread-count", headers=auth_headers_member)
    assert cnt_before.json()["unread_count"] == 1

    # Delete unread notification
    del_res = await client.delete(f"/api/v1/notifications/{nm1.id}", headers=auth_headers_member)
    assert del_res.status_code == 204

    # Unread count decrements to 0
    cnt_after = await client.get("/api/v1/notifications/unread-count", headers=auth_headers_member)
    assert cnt_after.json()["unread_count"] == 0

    # Only 1 notification remaining for member
    list_res = await client.get("/api/v1/notifications", headers=auth_headers_member)
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["id"] == seed_notifications_data["nm2"].id

    # Trying to delete already deleted notification -> 404
    del_again = await client.delete(f"/api/v1/notifications/{nm1.id}", headers=auth_headers_member)
    assert del_again.status_code == 404
    assert del_again.json()["error"]["message"] == "Notification not found."


# ==============================================================================
# 6. Intra-Tenant and Cross-Tenant Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_intra_and_cross_tenant_isolation(
    client: AsyncClient,
    auth_headers_owner: dict,
    auth_headers_member: dict,
    seed_notifications_data: dict,
):
    """Users cannot view, mark read, or delete notifications belonging to other users or other orgs."""
    data = seed_notifications_data
    n1 = data["n1"]      # belongs to Owner (Org A)
    nm1 = data["nm1"]    # belongs to Member (Org A)
    nb1 = data["nb1"]    # belongs to User Beta (Org B)

    # 1. Member cannot read Owner's notification (same org, different user) -> 404
    res1 = await client.patch(f"/api/v1/notifications/{n1.id}/read", headers=auth_headers_member)
    assert res1.status_code == 404
    assert res1.json()["error"]["message"] == "Notification not found."

    # 2. Member cannot delete Owner's notification -> 404
    res2 = await client.delete(f"/api/v1/notifications/{n1.id}", headers=auth_headers_member)
    assert res2.status_code == 404
    assert res2.json()["error"]["message"] == "Notification not found."

    # 3. Owner cannot read Member's notification -> 404
    res3 = await client.patch(f"/api/v1/notifications/{nm1.id}/read", headers=auth_headers_owner)
    assert res3.status_code == 404
    assert res3.json()["error"]["message"] == "Notification not found."

    # 4. Owner cannot delete Member's notification -> 404
    res4 = await client.delete(f"/api/v1/notifications/{nm1.id}", headers=auth_headers_owner)
    assert res4.status_code == 404
    assert res4.json()["error"]["message"] == "Notification not found."

    # 5. Owner cannot read Org B's notification -> 404
    res5 = await client.patch(f"/api/v1/notifications/{nb1.id}/read", headers=auth_headers_owner)
    assert res5.status_code == 404
    assert res5.json()["error"]["message"] == "Notification not found."

    # 6. Owner cannot delete Org B's notification -> 404
    res6 = await client.delete(f"/api/v1/notifications/{nb1.id}", headers=auth_headers_owner)
    assert res6.status_code == 404
    assert res6.json()["error"]["message"] == "Notification not found."

    # 7. Non-existent ID -> 404
    res_fake = await client.patch("/api/v1/notifications/non-existent-uuid-1234/read", headers=auth_headers_owner)
    assert res_fake.status_code == 404
    assert res_fake.json()["error"]["message"] == "Notification not found."
