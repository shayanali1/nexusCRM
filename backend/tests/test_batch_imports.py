"""Tests for Batch Ingestion Pipeline (CSV & Excel):
1. CSV upload, column detection, preview, and execution
2. In-tenant duplicate detection and duplicate row logging
3. Validation errors handling and detailed row audit logs
4. Excel (.xlsx) file ingestion
5. File size limits enforcement (>50MB rejected)
6. Cross-tenant isolation on import jobs and row audit logs
"""

import io
import os
import re
import pytest
from httpx import AsyncClient
import openpyxl
from sqlalchemy import func, select
from app.core.security import create_access_token, hash_password
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.imports.models import ImportJob, ImportRow
from app.modules.imports.service import ImportService
from app.modules.leads.models import Lead
from app.modules.organizations.models import Organization
from app.modules.users.models import User


@pytest.mark.asyncio
async def test_csv_upload_preview_and_execute_leads(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: dict,
    db_session,
):
    """Test full flow: upload CSV, dry-run preview, execute ingestion, verify database leads."""
    csv_content = (
        "Full Name,Work Email,Phone Number,Company,Value\n"
        "Sarah Connor,sarah@skynet-defense.com,555-1001,Cyberdyne Systems,50000\n"
        "Kyle Reese,kyle@resistance.org,555-1002,Tech Resistance,35000\n"
    )

    # 1. Upload CSV
    files = {"file": ("leads_sample.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    upload_res = await client.post(
        "/api/v1/imports/upload",
        files=files,
        data={"entity_type": "leads"},
        headers=auth_headers_owner,
    )
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    job_id = upload_data["job_id"]
    assert "Full Name" in upload_data["detected_headers"]
    assert "Work Email" in upload_data["detected_headers"]
    assert upload_data["total_rows_estimated"] == 2

    # 2. Dry-run preview with mapping
    mapping = {
        "Full Name": "contact_name",
        "Work Email": "contact_email",
        "Phone Number": "contact_phone",
        "Company": "company",
        "Value": "value",
    }
    preview_res = await client.post(
        f"/api/v1/imports/{job_id}/preview",
        json={"mapping": mapping},
        headers=auth_headers_owner,
    )
    assert preview_res.status_code == 200
    preview_data = preview_res.json()
    assert preview_data["total_samples"] == 2
    assert preview_data["preview_rows"][0]["is_valid"] is True
    assert preview_data["preview_rows"][0]["is_duplicate"] is False

    # 3. Execute ingestion
    exec_res = await client.post(
        f"/api/v1/imports/{job_id}/execute",
        json={"mapping": mapping, "background": False},
        headers=auth_headers_owner,
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "COMPLETED"
    assert exec_data["successful_rows"] == 2
    assert exec_data["failed_rows"] == 0
    assert exec_data["duplicate_rows"] == 0

    # 4. Verify entities in database
    leads_stmt = select(Lead).where(Lead.organization_id == test_org.id)
    leads = (await db_session.execute(leads_stmt)).scalars().all()
    assert len(leads) == 2

    # 5. Verify row audit log endpoint
    rows_res = await client.get(
        f"/api/v1/imports/{job_id}/rows",
        headers=auth_headers_owner,
    )
    assert rows_res.status_code == 200
    rows = rows_res.json()
    assert len(rows) == 2
    assert all(r["status"] == "SUCCESS" for r in rows)


@pytest.mark.asyncio
async def test_csv_duplicate_and_error_handling(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: dict,
    db_session,
):
    """Test that existing contacts/leads are flagged as DUPLICATE and invalid emails as ERROR."""
    # Pre-create contact in tenant
    existing_contact = Contact(
        organization_id=test_org.id,
        first_name="Gordon",
        last_name="Freeman",
        email="gordon@blackmesa.gov",
    )
    db_session.add(existing_contact)
    await db_session.commit()

    # CSV with: 1 duplicate, 1 invalid email, 1 valid contact
    csv_content = (
        "Name,Email,Phone\n"
        "Gordon Freeman,gordon@blackmesa.gov,555-0101\n"  # DUPLICATE
        "Barney Calhoun,not-an-email,555-0102\n"  # ERROR: invalid email
        "Alyx Vance,alyx@city17.org,555-0103\n"  # SUCCESS
    )

    files = {"file": ("contacts.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    upload_res = await client.post(
        "/api/v1/imports/upload",
        files=files,
        data={"entity_type": "contacts"},
        headers=auth_headers_owner,
    )
    assert upload_res.status_code == 201
    job_id = upload_res.json()["job_id"]

    mapping = {"Name": "name", "Email": "email", "Phone": "phone"}
    exec_res = await client.post(
        f"/api/v1/imports/{job_id}/execute",
        json={"mapping": mapping},
        headers=auth_headers_owner,
    )
    assert exec_res.status_code == 200
    data = exec_res.json()
    assert data["total_rows"] == 3
    assert data["successful_rows"] == 1
    assert data["duplicate_rows"] == 1
    assert data["failed_rows"] == 1

    # Verify row audit logs
    rows_res = await client.get(
        f"/api/v1/imports/{job_id}/rows",
        headers=auth_headers_owner,
    )
    assert rows_res.status_code == 200
    rows = rows_res.json()
    statuses = {r["row_number"]: r["status"] for r in rows}
    assert statuses[1] == "DUPLICATE"
    assert statuses[2] == "ERROR"
    assert statuses[3] == "SUCCESS"


@pytest.mark.asyncio
async def test_excel_xlsx_import(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: dict,
    db_session,
):
    """Test importing data from a real Excel (.xlsx) spreadsheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Companies"
    ws.append(["Company Name", "Domain", "Industry", "City"])
    ws.append(["Stark Industries", "starkindustries.com", "Aerospace", "New York"])
    ws.append(["Wayne Enterprises", "wayneenterprises.com", "Defense", "Gotham"])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    files = {"file": ("companies.xlsx", buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    upload_res = await client.post(
        "/api/v1/imports/upload",
        files=files,
        data={"entity_type": "companies"},
        headers=auth_headers_owner,
    )
    assert upload_res.status_code == 201
    job_id = upload_res.json()["job_id"]

    mapping = {"Company Name": "name", "Domain": "domain", "Industry": "industry", "City": "city"}
    exec_res = await client.post(
        f"/api/v1/imports/{job_id}/execute",
        json={"mapping": mapping},
        headers=auth_headers_owner,
    )
    assert exec_res.status_code == 200
    assert exec_res.json()["successful_rows"] == 2

    # Verify in DB
    companies = (await db_session.execute(
        select(Company).where(Company.organization_id == test_org.id)
    )).scalars().all()
    company_names = [c.name for c in companies]
    assert "Stark Industries" in company_names
    assert "Wayne Enterprises" in company_names


@pytest.mark.asyncio
async def test_oversized_file_rejected(
    client: AsyncClient,
    auth_headers_owner: dict,
):
    """Test that files exceeding 50MB limit are strictly rejected."""
    # Create fake oversized content in memory (51MB)
    oversized_content = b"x" * (51 * 1024 * 1024)
    files = {"file": ("huge_file.csv", io.BytesIO(oversized_content), "text/csv")}

    upload_res = await client.post(
        "/api/v1/imports/upload",
        files=files,
        data={"entity_type": "leads"},
        headers=auth_headers_owner,
    )
    assert upload_res.status_code == 400
    assert "exceeds maximum limit" in upload_res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_cross_tenant_import_isolation(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: dict,
    db_session,
):
    """Verify that Organization B cannot access Organization A's import job or row logs."""
    # Create Organization B and user
    org_b = Organization(name="Beta Corp", slug="beta-corp", plan="starter", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    user_b = User(
        organization_id=org_b.id,
        email="admin@betacorp.com",
        hashed_password=hash_password("password123"),
        first_name="Bob",
        last_name="Beta",
        role="OWNER",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user_b)
    await db_session.commit()

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)
    auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    # Org A uploads file
    csv_content = "Name,Email\nTarget Contact,target@orgA.com\n"
    files = {"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    upload_res = await client.post(
        "/api/v1/imports/upload",
        files=files,
        data={"entity_type": "contacts"},
        headers=auth_headers_owner,
    )
    assert upload_res.status_code == 201
    job_id = upload_res.json()["job_id"]

    # Org B attempts to read Org A's import job
    get_res = await client.get(
        f"/api/v1/imports/{job_id}",
        headers=auth_headers_b,
    )
    assert get_res.status_code == 404

    # Org B attempts to read Org A's import rows
    rows_res = await client.get(
        f"/api/v1/imports/{job_id}/rows",
        headers=auth_headers_b,
    )
    assert rows_res.status_code == 404


@pytest.mark.asyncio
async def test_uploaded_filename_traversal_sanitization(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
):
    """Test that uploaded filenames with path traversal (POSIX & Windows) do not escape tenant directory."""
    csv_content = "Full Name,Work Email\nTraverse Lead,traverse@example.com\n"
    tenant_upload_dir = os.path.realpath(os.path.abspath(os.path.join(os.getcwd(), "uploads", "imports", test_org.id)))

    # 1. POSIX traversal attempt
    posix_traversal_name = "../../traversal_test.csv"
    files_posix = {"file": (posix_traversal_name, io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res_posix = await client.post(
        "/api/v1/imports/upload",
        files=files_posix,
        data={"entity_type": "leads"},
        headers=auth_headers_owner,
    )
    assert res_posix.status_code == 201
    job_id_posix = res_posix.json()["job_id"]

    # Verify POSIX job storage path in DB
    job_posix = (await db_session.execute(select(ImportJob).where(ImportJob.id == job_id_posix))).scalar_one()
    # Preserves original filename safely in metadata/database record
    assert job_posix.file_name == posix_traversal_name
    # Filesystem path must be canonicalized and strictly inside tenant directory
    canonical_posix_path = os.path.realpath(job_posix.file_path)
    assert os.path.commonpath([tenant_upload_dir, canonical_posix_path]) == tenant_upload_dir
    assert os.path.dirname(canonical_posix_path) == tenant_upload_dir
    # Stored filename must be server-controlled UUID + extension
    stored_name_posix = os.path.basename(canonical_posix_path)
    assert re.match(r"^[0-9a-f]{32}\.csv$", stored_name_posix)
    assert os.path.isfile(canonical_posix_path)

    # 2. Windows traversal attempt
    win_traversal_name = r"..\..\win_traversal_test.csv"
    files_win = {"file": (win_traversal_name, io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res_win = await client.post(
        "/api/v1/imports/upload",
        files=files_win,
        data={"entity_type": "leads"},
        headers=auth_headers_owner,
    )
    assert res_win.status_code == 201
    job_id_win = res_win.json()["job_id"]

    # Verify Windows job storage path in DB
    job_win = (await db_session.execute(select(ImportJob).where(ImportJob.id == job_id_win))).scalar_one()
    assert job_win.file_name == win_traversal_name
    canonical_win_path = os.path.realpath(job_win.file_path)
    assert os.path.commonpath([tenant_upload_dir, canonical_win_path]) == tenant_upload_dir
    assert os.path.dirname(canonical_win_path) == tenant_upload_dir
    stored_name_win = os.path.basename(canonical_win_path)
    assert re.match(r"^[0-9a-f]{32}\.csv$", stored_name_win)
    assert os.path.isfile(canonical_win_path)


@pytest.mark.asyncio
async def test_invalid_and_dangerous_filenames_rejected(
    client: AsyncClient,
    auth_headers_owner: dict,
):
    """Test that empty, invalid, and unsupported executable file extensions are rejected."""
    csv_bytes = b"Full Name,Work Email\nBad File,bad@example.com\n"

    # Unsupported extension
    res_exe = await client.post(
        "/api/v1/imports/upload",
        files={"file": ("malicious.exe", io.BytesIO(csv_bytes), "application/octet-stream")},
        data={"entity_type": "leads"},
        headers=auth_headers_owner,
    )
    assert res_exe.status_code == 400
    assert "Unsupported file format" in res_exe.json()["error"]["message"]

    # Traversal into unsupported extension
    res_sh = await client.post(
        "/api/v1/imports/upload",
        files={"file": ("../../run.sh", io.BytesIO(csv_bytes), "text/plain")},
        data={"entity_type": "leads"},
        headers=auth_headers_owner,
    )
    assert res_sh.status_code == 400
    assert "Unsupported file format" in res_sh.json()["error"]["message"]

    # Extension spoofing / double extension
    res_double = await client.post(
        "/api/v1/imports/upload",
        files={"file": ("data.csv.bat", io.BytesIO(csv_bytes), "application/octet-stream")},
        data={"entity_type": "leads"},
        headers=auth_headers_owner,
    )
    assert res_double.status_code == 400
    assert "Unsupported file format" in res_double.json()["error"]["message"]


@pytest.mark.asyncio
async def test_reject_reexecution_of_completed_job(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
):
    """Test that a completed import job cannot be re-executed, preventing duplicate entities and duplicate audit rows."""
    csv_content = (
        "Full Name,Work Email\n"
        "Sarah Connor,sarah@skynet.org\n"
        "Kyle Reese,kyle@skynet.org\n"
    )
    files = {"file": ("leads.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    upload_res = await client.post(
        "/api/v1/imports/upload",
        files=files,
        data={"entity_type": "leads"},
        headers=auth_headers_owner,
    )
    assert upload_res.status_code == 201
    job_id = upload_res.json()["job_id"]

    org_id = str(test_org.id)
    mapping = {"Full Name": "contact_name", "Work Email": "contact_email"}

    # 1. First execution succeeds
    exec_res1 = await client.post(
        f"/api/v1/imports/{job_id}/execute",
        json={"mapping": mapping, "background": False},
        headers=auth_headers_owner,
    )
    assert exec_res1.status_code == 200
    data1 = exec_res1.json()
    assert data1["status"] == "COMPLETED"
    assert data1["successful_rows"] == 2
    assert data1["failed_rows"] == 0
    assert data1["duplicate_rows"] == 0

    # Verify initial database state
    leads_before = (await db_session.execute(select(Lead).where(Lead.organization_id == org_id))).scalars().all()
    assert len(leads_before) == 2

    rows_before = (await db_session.execute(select(ImportRow).where(ImportRow.import_job_id == job_id))).scalars().all()
    assert len(rows_before) == 2

    job_before = (await db_session.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    assert job_before.status == "COMPLETED"
    assert job_before.processed_rows == 2
    assert job_before.successful_rows == 2

    # 2. Second execution attempt (synchronous) MUST be rejected with 400
    exec_res2 = await client.post(
        f"/api/v1/imports/{job_id}/execute",
        json={"mapping": mapping, "background": False},
        headers=auth_headers_owner,
    )
    assert exec_res2.status_code == 400
    assert "Cannot execute an import job that has already completed." in exec_res2.json()["error"]["message"]

    # 3. Third execution attempt (background) MUST ALSO be rejected with 400
    exec_res3 = await client.post(
        f"/api/v1/imports/{job_id}/execute",
        json={"mapping": mapping, "background": True},
        headers=auth_headers_owner,
    )
    assert exec_res3.status_code == 400
    assert "Cannot execute an import job that has already completed." in exec_res3.json()["error"]["message"]

    # 4. Direct service call MUST also raise BadRequestException
    service = ImportService(db_session, org_id)
    with pytest.raises(Exception) as exc_info:
        await service.execute_import(job_id, mapping)
    assert "Cannot execute an import job that has already completed." in str(exc_info.value)

    # 5. Verify database records are strictly unchanged: no duplicate leads, no duplicate rows, unchanged counters
    leads_after = (await db_session.execute(select(Lead).where(Lead.organization_id == org_id))).scalars().all()
    assert len(leads_after) == 2

    rows_after = (await db_session.execute(select(ImportRow).where(ImportRow.import_job_id == job_id))).scalars().all()
    assert len(rows_after) == 2

    job_after = (await db_session.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    assert job_after.status == "COMPLETED"
    assert job_after.processed_rows == 2
    assert job_after.successful_rows == 2
    assert job_after.failed_rows == 0
    assert job_after.duplicate_rows == 0


@pytest.mark.asyncio
async def test_failed_job_retry_allowed(
    test_org: Organization,
    test_user_owner: User,
    db_session,
):
    """Test that a failed import job is allowed to be retried (not blocked by COMPLETED check)."""
    # Create a job with FAILED status
    csv_content = "Full Name,Work Email\nRetry Lead,retry@skynet.org\n"
    upload_dir = os.path.realpath(os.path.abspath(os.path.join(os.getcwd(), "uploads", "imports", test_org.id)))
    os.makedirs(upload_dir, exist_ok=True)
    csv_path = os.path.join(upload_dir, "retry_test.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(csv_content)

    failed_job = ImportJob(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        entity_type="leads",
        file_name="retry_test.csv",
        file_path=csv_path,
        status="FAILED",
        total_rows=1,
    )
    db_session.add(failed_job)
    await db_session.commit()
    await db_session.refresh(failed_job)

    # Execute should succeed and transition to COMPLETED
    service = ImportService(db_session, test_org.id)
    mapping = {"Full Name": "contact_name", "Work Email": "contact_email"}
    retried_job = await service.execute_import(failed_job.id, mapping)
    assert retried_job.status == "COMPLETED"
    assert retried_job.successful_rows == 1
