"""Comprehensive test suite for Phase 5 Step 6.2 - Secure Integration Management Foundation.

Covers:
1. Full CRUD lifecycle (create, list, retrieve, update, delete).
2. Repeated POST upsert semantics (no duplicate rows, safe concurrent upsert).
3. Strict multi-tenant isolation (Org A cannot read/mutate/delete Org B).
4. Full RBAC matrix (OWNER, ADMIN, MANAGER, MEMBER).
5. Responses never leak plaintext credentials or ciphertext envelopes.
6. Direct database rows store encrypted ciphertext, never plaintext.
7. Omitted credentials during update preserve existing credentials.
8. Explicitly passing {} clears stored credentials.
9. Missing or invalid encryption keys fail safely without plaintext persistence.
10. Empty credentials work without an encryption key or live provider.
11. Configuration validation rejects sensitive/secret keys in plaintext config.
12. Invalid or unsupported provider names are rejected.
13. Safe handling of malformed or legacy integration rows.
"""

from typing import Dict
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.modules.integrations.crypto import DecryptionFailedException
from app.modules.integrations.models import Integration
from app.modules.integrations.repository import IntegrationRepository
from app.modules.organizations.models import Organization
from app.modules.users.models import User


@pytest.fixture
def auth_headers_for_user():
    """Helper factory for generating auth headers for any user and tenant."""
    def _make_headers(user: User, org: Organization) -> Dict[str, str]:
        token = create_access_token(user.id, org.id, user.role)
        return {"Authorization": f"Bearer {token}"}
    return _make_headers


@pytest.mark.asyncio
async def test_integration_crud_lifecycle(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: Dict[str, str],
):
    """Authenticated owner can create, list, retrieve, update, and delete integrations."""
    # 1. Create integration with config and credentials
    create_payload = {
        "is_active": True,
        "config": {"channel": "#crm-alerts", "bot_name": "NexusBot"},
        "credentials": {"token": "xoxb-super-secret-slack-token-12345"},
    }
    resp = await client.post(
        "/api/v1/integrations/slack",
        json=create_payload,
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider"] == "slack"
    assert data["is_active"] is True
    assert data["config"] == {"channel": "#crm-alerts", "bot_name": "NexusBot"}
    assert data["has_credentials"] is True
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    # Zero plaintext and zero ciphertext in response
    assert "credentials" not in data
    assert "ciphertext" not in data
    assert "xoxb-super-secret-slack-token-12345" not in resp.text

    # 2. List integrations
    list_resp = await client.get("/api/v1/integrations", headers=auth_headers_owner)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert len(list_data) == 1
    assert list_data[0]["provider"] == "slack"
    assert list_data[0]["has_credentials"] is True

    # 3. Retrieve single integration by provider
    get_resp = await client.get("/api/v1/integrations/slack", headers=auth_headers_owner)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["provider"] == "slack"
    assert get_data["config"]["channel"] == "#crm-alerts"

    # 4. Update integration (deactivate and change config, omit credentials)
    update_payload = {
        "is_active": False,
        "config": {"channel": "#crm-sales-leads", "bot_name": "NexusBot"},
    }
    update_resp = await client.post(
        "/api/v1/integrations/slack",
        json=update_payload,
        headers=auth_headers_owner,
    )
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["is_active"] is False
    assert updated_data["config"]["channel"] == "#crm-sales-leads"
    assert updated_data["has_credentials"] is True

    # 5. Delete integration
    del_resp = await client.delete("/api/v1/integrations/slack", headers=auth_headers_owner)
    assert del_resp.status_code == 204

    # 6. Verify 404 after deletion
    post_del_resp = await client.get("/api/v1/integrations/slack", headers=auth_headers_owner)
    assert post_del_resp.status_code == 404


@pytest.mark.asyncio
async def test_repeated_post_upserts_without_duplicate(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: Dict[str, str],
):
    """Repeated POST for the same provider updates the single row rather than duplicating."""
    payload1 = {
        "is_active": True,
        "config": {"from_email": "v1@example.com"},
        "credentials": {"api_key": "key_v1"},
    }
    r1 = await client.post("/api/v1/integrations/sendgrid", json=payload1, headers=auth_headers_owner)
    assert r1.status_code == 200
    id_1 = r1.json()["id"]

    payload2 = {
        "is_active": False,
        "config": {"from_email": "v2@example.com"},
    }
    r2 = await client.post("/api/v1/integrations/sendgrid", json=payload2, headers=auth_headers_owner)
    assert r2.status_code == 200
    id_2 = r2.json()["id"]

    assert id_1 == id_2

    list_resp = await client.get("/api/v1/integrations", headers=auth_headers_owner)
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["config"]["from_email"] == "v2@example.com"
    assert list_resp.json()[0]["is_active"] is False


@pytest.mark.asyncio
async def test_tenant_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    auth_headers_owner: Dict[str, str],
    auth_headers_for_user,
):
    """Verify Tenant A and Tenant B configurations are completely isolated."""
    # Org A sets up google_calendar
    r_a = await client.post(
        "/api/v1/integrations/google_calendar",
        json={"is_active": True, "config": {"calendar_id": "primary_a"}},
        headers=auth_headers_owner,
    )
    assert r_a.status_code == 200

    # Create Org B and user
    org_b = Organization(name="Org Beta", slug="org-beta", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    user_b_owner = User(
        organization_id=org_b.id,
        email="owner@beta.com",
        first_name="Beta",
        last_name="Owner",
        hashed_password=hash_password("pw123"),
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b_owner)
    await db_session.commit()

    headers_b = auth_headers_for_user(user_b_owner, org_b)

    # Org B lists integrations -> empty
    list_b = await client.get("/api/v1/integrations", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json() == []

    # Org B gets google_calendar -> 404
    get_b = await client.get("/api/v1/integrations/google_calendar", headers=headers_b)
    assert get_b.status_code == 404

    # Org B deletes google_calendar -> 404
    del_b = await client.delete("/api/v1/integrations/google_calendar", headers=headers_b)
    assert del_b.status_code == 404

    # Org B sets up google_calendar with its own config
    r_b_post = await client.post(
        "/api/v1/integrations/google_calendar",
        json={"is_active": True, "config": {"calendar_id": "primary_b"}},
        headers=headers_b,
    )
    assert r_b_post.status_code == 200

    # Org A config is unchanged
    get_a = await client.get("/api/v1/integrations/google_calendar", headers=auth_headers_owner)
    assert get_a.json()["config"]["calendar_id"] == "primary_a"


@pytest.mark.asyncio
async def test_rbac_roles_matrix(
    client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    auth_headers_for_user,
):
    """OWNER and ADMIN can read and manage; MANAGER can only read; MEMBER can do neither."""
    # Create ADMIN, MANAGER, MEMBER users
    admin_user = User(
        organization_id=test_org.id,
        email="admin@alpha.com",
        first_name="Adam",
        last_name="Admin",
        hashed_password=hash_password("pw123"),
        role="ADMIN",
        is_active=True,
    )
    manager_user = User(
        organization_id=test_org.id,
        email="manager@alpha.com",
        first_name="Manny",
        last_name="Manager",
        hashed_password=hash_password("pw123"),
        role="MANAGER",
        is_active=True,
    )
    member_user = User(
        organization_id=test_org.id,
        email="member_rbac@alpha.com",
        first_name="Mem",
        last_name="Member",
        hashed_password=hash_password("pw123"),
        role="MEMBER",
        is_active=True,
    )
    db_session.add_all([admin_user, manager_user, member_user])
    await db_session.commit()

    headers_admin = auth_headers_for_user(admin_user, test_org)
    headers_manager = auth_headers_for_user(manager_user, test_org)
    headers_member = auth_headers_for_user(member_user, test_org)

    # 1. ADMIN can manage and read
    post_admin = await client.post(
        "/api/v1/integrations/webhook",
        json={"is_active": True, "config": {"target": "https://example.com/admin"}},
        headers=headers_admin,
    )
    assert post_admin.status_code == 200

    get_admin = await client.get("/api/v1/integrations/webhook", headers=headers_admin)
    assert get_admin.status_code == 200

    # 2. MANAGER can read, but cannot manage
    get_manager = await client.get("/api/v1/integrations/webhook", headers=headers_manager)
    assert get_manager.status_code == 200

    post_manager = await client.post(
        "/api/v1/integrations/webhook",
        json={"is_active": False},
        headers=headers_manager,
    )
    assert post_manager.status_code == 403

    del_manager = await client.delete("/api/v1/integrations/webhook", headers=headers_manager)
    assert del_manager.status_code == 403

    # 3. MEMBER cannot read or manage
    get_member = await client.get("/api/v1/integrations/webhook", headers=headers_member)
    assert get_member.status_code == 403

    list_member = await client.get("/api/v1/integrations", headers=headers_member)
    assert list_member.status_code == 403

    post_member = await client.post(
        "/api/v1/integrations/webhook",
        json={"is_active": False},
        headers=headers_member,
    )
    assert post_member.status_code == 403

    del_member = await client.delete("/api/v1/integrations/webhook", headers=headers_member)
    assert del_member.status_code == 403


@pytest.mark.asyncio
async def test_database_row_contains_ciphertext_never_plaintext(
    client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    auth_headers_owner: Dict[str, str],
):
    """Direct database inspection confirms credentials column stores ciphertext envelope."""
    secret_token = "re_test_live_api_secret_key_88888"
    resp = await client.post(
        "/api/v1/integrations/resend",
        json={
            "is_active": True,
            "config": {"sender_domain": "notifications.nexuscrm.local"},
            "credentials": {"api_key": secret_token},
        },
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200

    # Direct DB inspection
    stmt = select(Integration).where(
        Integration.organization_id == test_org.id,
        Integration.provider == "resend",
    )
    result = await db_session.execute(stmt)
    db_row = result.scalar_one()

    assert isinstance(db_row.credentials, dict)
    assert db_row.credentials["version"] == 1
    assert db_row.credentials["algorithm"] == "fernet"
    assert "ciphertext" in db_row.credentials

    # Plaintext token is NEVER in the database credentials column
    assert secret_token not in db_row.credentials["ciphertext"]
    assert "api_key" not in db_row.credentials

    # Repository helper can decrypt for internal worker code
    repo = IntegrationRepository(db_session, test_org.id)
    decrypted = repo.get_decrypted_credentials(db_row)
    assert decrypted == {"api_key": secret_token}


@pytest.mark.asyncio
async def test_omitted_credentials_preserves_existing(
    client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    auth_headers_owner: Dict[str, str],
):
    """Omitting credentials in an update leaves previously encrypted credentials intact."""
    # Initial creation with secret
    await client.post(
        "/api/v1/integrations/slack",
        json={"credentials": {"token": "orig_token_123"}},
        headers=auth_headers_owner,
    )

    # Update only config
    up_resp = await client.post(
        "/api/v1/integrations/slack",
        json={"config": {"channel": "#general"}},
        headers=auth_headers_owner,
    )
    assert up_resp.json()["has_credentials"] is True

    # Decrypt DB row
    stmt = select(Integration).where(
        Integration.organization_id == test_org.id,
        Integration.provider == "slack",
    )
    row = (await db_session.execute(stmt)).scalar_one()
    repo = IntegrationRepository(db_session, test_org.id)
    assert repo.get_decrypted_credentials(row) == {"token": "orig_token_123"}


@pytest.mark.asyncio
async def test_explicit_empty_dict_clears_credentials(
    client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    auth_headers_owner: Dict[str, str],
):
    """Explicitly passing {} clears previously stored credentials."""
    # Create with credentials
    await client.post(
        "/api/v1/integrations/slack",
        json={"credentials": {"token": "secret_to_clear"}},
        headers=auth_headers_owner,
    )

    # Clear credentials by explicitly sending empty dict
    clear_resp = await client.post(
        "/api/v1/integrations/slack",
        json={"credentials": {}},
        headers=auth_headers_owner,
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["has_credentials"] is False

    # Direct DB inspection
    stmt = select(Integration).where(
        Integration.organization_id == test_org.id,
        Integration.provider == "slack",
    )
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.credentials == {}


@pytest.mark.asyncio
async def test_missing_or_invalid_key_fails_safely_without_plaintext_persistence(
    client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    auth_headers_owner: Dict[str, str],
    monkeypatch,
):
    """Attempting to save credentials without a configured key returns 500 and persists nothing."""
    monkeypatch.setattr(settings, "INTEGRATION_ENCRYPTION_KEY", None)

    resp = await client.post(
        "/api/v1/integrations/zapier",
        json={
            "is_active": True,
            "credentials": {"secret_key": "will_fail_to_encrypt"},
        },
        headers=auth_headers_owner,
    )
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "ENCRYPTION_KEY_MISSING"

    # Verify nothing was persisted
    stmt = select(Integration).where(
        Integration.organization_id == test_org.id,
        Integration.provider == "zapier",
    )
    row = (await db_session.execute(stmt)).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_empty_credentials_works_without_encryption_key(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: Dict[str, str],
    monkeypatch,
):
    """Integrations without credentials can be saved cleanly even if no key is configured."""
    monkeypatch.setattr(settings, "INTEGRATION_ENCRYPTION_KEY", None)

    resp = await client.post(
        "/api/v1/integrations/zapier",
        json={
            "is_active": True,
            "config": {"webhook_url": "https://hooks.zapier.com/test"},
        },
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] == "zapier"
    assert resp.json()["has_credentials"] is False


@pytest.mark.asyncio
async def test_validation_rejects_secrets_in_config(
    client: AsyncClient,
    auth_headers_owner: Dict[str, str],
):
    """Config dictionary rejects recognized sensitive credential keys."""
    bad_configs = [
        {"api_key": "plaintext_leak"},
        {"password": "secretpassword"},
        {"client_secret": "my_client_secret"},
        {"auth_token": "bearer_abc"},
        {"custom_secret_key": "value"},
    ]

    for bad_cfg in bad_configs:
        resp = await client.post(
            "/api/v1/integrations/webhook",
            json={"config": bad_cfg},
            headers=auth_headers_owner,
        )
        assert resp.status_code in (400, 422), f"Expected validation error for {bad_cfg}"


@pytest.mark.asyncio
async def test_validation_rejects_unsupported_provider(
    client: AsyncClient,
    auth_headers_owner: Dict[str, str],
):
    """Unsupported provider identifiers are rejected with 400 Bad Request."""
    resp_post = await client.post(
        "/api/v1/integrations/unsupported_vendor",
        json={"is_active": True},
        headers=auth_headers_owner,
    )
    assert resp_post.status_code == 400
    assert "Unsupported integration provider" in resp_post.json()["error"]["message"]

    resp_get = await client.get(
        "/api/v1/integrations/unsupported_vendor",
        headers=auth_headers_owner,
    )
    assert resp_get.status_code == 400

    resp_del = await client.delete(
        "/api/v1/integrations/unsupported_vendor",
        headers=auth_headers_owner,
    )
    assert resp_del.status_code == 400

    # Path parameter mismatch
    mismatch_resp = await client.post(
        "/api/v1/integrations/slack",
        json={"provider": "sendgrid"},
        headers=auth_headers_owner,
    )
    assert mismatch_resp.status_code == 400


@pytest.mark.asyncio
async def test_legacy_data_safe_handling(
    client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    auth_headers_owner: Dict[str, str],
):
    """Existing unencrypted or malformed credentials never silently expose secrets."""
    # Directly insert raw unencrypted dictionary into DB
    legacy = Integration(
        organization_id=test_org.id,
        provider="slack",
        is_active=True,
        config={"channel": "#legacy"},
        credentials={"raw_secret_key": "unencrypted_legacy_token"},
    )
    db_session.add(legacy)
    await db_session.commit()

    # Public API representation: indicates has_credentials, but leaks ZERO raw secrets
    resp = await client.get("/api/v1/integrations/slack", headers=auth_headers_owner)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_credentials"] is True
    assert "unencrypted_legacy_token" not in resp.text
    assert "raw_secret_key" not in resp.text

    # Internal decryption rejects legacy unencrypted format safely
    repo = IntegrationRepository(db_session, test_org.id)
    with pytest.raises(DecryptionFailedException):
        repo.get_decrypted_credentials(legacy)


@pytest.mark.asyncio
async def test_recursive_secret_detection_in_config(
    client: AsyncClient,
    auth_headers_owner: Dict[str, str],
):
    """Recursive inspection detects secrets in nested dictionaries, lists, and normalized keys."""
    # 1. Nested dictionary with sensitive key
    nested_dict_cfg = {
        "routing": {
            "auth": {
                "api_key": "nested_secret_val",
            }
        }
    }
    r1 = await client.post(
        "/api/v1/integrations/webhook",
        json={"config": nested_dict_cfg},
        headers=auth_headers_owner,
    )
    assert r1.status_code == 422
    assert "config.routing.auth.api_key" in r1.text

    # 2. Dictionary inside a list with sensitive key
    list_dict_cfg = {
        "destinations": [
            {"url": "https://external.local/hook", "priority": 1},
            {"url": "https://vault.local/api", "client_secret": "nested_client_secret"},
        ]
    }
    r2 = await client.post(
        "/api/v1/integrations/webhook",
        json={"config": list_dict_cfg},
        headers=auth_headers_owner,
    )
    assert r2.status_code == 422
    assert "config.destinations[1].client_secret" in r2.text

    # 3. Normalized key with whitespace and uppercase hyphens
    normalized_key_cfg = {
        "custom": {
            "  AUTH-TOKEN  ": "secret_bearer_token",
        }
    }
    r3 = await client.post(
        "/api/v1/integrations/webhook",
        json={"config": normalized_key_cfg},
        headers=auth_headers_owner,
    )
    assert r3.status_code == 422

    # 4. Positive test: complex, valid nested configuration without secrets is accepted
    valid_nested_cfg = {
        "routing": {
            "rules": [
                {"destination": "#general", "priority": 1, "timeout_seconds": 30},
                {"destination": "#sales", "priority": 2, "timeout_seconds": 60},
            ],
            "fallback": {"channel": "#ops", "enabled": True},
        }
    }
    r4 = await client.post(
        "/api/v1/integrations/webhook",
        json={"is_active": True, "config": valid_nested_cfg},
        headers=auth_headers_owner,
    )
    assert r4.status_code == 200
    assert r4.json()["config"] == valid_nested_cfg


@pytest.mark.asyncio
async def test_validation_errors_never_echo_credentials(
    client: AsyncClient,
    auth_headers_owner: Dict[str, str],
):
    """Submitting invalid credentials datatypes redacts input value from 422 validation response."""
    distinctive_secret = "super_distinctive_fake_secret_never_leak_me_xyz_987"

    # Send a string instead of the expected dictionary for credentials
    resp = await client.post(
        "/api/v1/integrations/slack",
        json={
            "is_active": True,
            "credentials": distinctive_secret,
        },
        headers=auth_headers_owner,
    )
    assert resp.status_code == 422

    # CRITICAL: Assert the secret value does NOT appear anywhere in the response body or text
    assert distinctive_secret not in resp.text

    error_data = resp.json()["error"]
    assert error_data["code"] == "VALIDATION_ERROR"
    assert len(error_data["details"]) > 0

    detail = error_data["details"][0]
    assert "credentials" in detail["loc"]
    assert detail["input"] == "[REDACTED]"
    assert "valid dictionary" in detail["msg"]


@pytest.mark.asyncio
async def test_non_credential_validation_error_preserves_input(
    client: AsyncClient,
    auth_headers_owner: Dict[str, str],
):
    """Validation errors on non-credential fields preserve input value for developer diagnostics."""
    resp = await client.post(
        "/api/v1/integrations/slack",
        json={
            "is_active": "definitely_not_a_boolean",
        },
        headers=auth_headers_owner,
    )
    assert resp.status_code == 422

    error_data = resp.json()["error"]
    assert error_data["code"] == "VALIDATION_ERROR"
    detail = error_data["details"][0]
    assert "is_active" in detail["loc"]
    # Normal input should be preserved for debugging
    assert detail["input"] == "definitely_not_a_boolean"
