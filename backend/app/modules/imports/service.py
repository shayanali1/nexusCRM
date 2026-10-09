"""Batch Ingestion Service (CSV/XLSX).

Handles file storage, schema validation, dry-run previews,
in-tenant duplicate detection, and execution across Leads, Contacts, and Companies.
"""

from datetime import datetime, timezone
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import logger
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.imports.models import ImportJob, ImportRow
from app.modules.imports.parser import get_headers_and_sample, read_all_rows
from app.modules.imports.schemas import ImportPreviewResponse, ImportPreviewRow
from app.modules.leads.models import Lead, LeadPriority, LeadStatus

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB limit
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
VALID_ENTITIES = {"leads", "contacts", "companies"}


class ImportService:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def create_upload_job(
        self,
        user_id: str,
        file_name: str,
        file_content: bytes,
        entity_type: str,
    ) -> Tuple[ImportJob, List[str], List[Dict[str, Any]], int]:
        """Validate uploaded file, save securely to disk, and register initial ImportJob."""
        if entity_type not in VALID_ENTITIES:
            raise BadRequestException(f"Invalid entity_type '{entity_type}'. Must be one of {list(VALID_ENTITIES)}")

        if len(file_content) > MAX_FILE_SIZE_BYTES:
            raise BadRequestException(
                f"File size ({len(file_content) / (1024*1024):.1f}MB) exceeds maximum limit of 50MB."
            )

        if not file_name or not file_name.strip() or "\x00" in file_name:
            raise BadRequestException("Empty or invalid filename.")

        # Normalize path separators across POSIX (/) and Windows (\)
        normalized_name = file_name.replace("\\", "/").strip()
        base_name = os.path.basename(normalized_name.rstrip("/"))
        if not base_name:
            raise BadRequestException("Empty or invalid filename.")

        ext = os.path.splitext(base_name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise BadRequestException(
                f"Unsupported file format '{ext}'. Allowed extensions: {list(ALLOWED_EXTENSIONS)}"
            )

        # Store in tenant isolated directory using server-controlled unique UUID
        upload_dir = os.path.realpath(os.path.abspath(os.path.join(os.getcwd(), "uploads", "imports", self.org_id)))
        os.makedirs(upload_dir, exist_ok=True)

        stored_file_name = f"{uuid.uuid4().hex}{ext}"
        saved_path = os.path.realpath(os.path.join(upload_dir, stored_file_name))

        # Enforce that the resolved path stays strictly inside the tenant upload directory
        if os.path.commonpath([upload_dir, saved_path]) != upload_dir or saved_path == upload_dir:
            raise BadRequestException("Target storage path outside tenant directory.")

        with open(saved_path, "wb") as f:
            f.write(file_content)

        headers, samples, total_rows = get_headers_and_sample(saved_path, sample_limit=10)

        job = ImportJob(
            organization_id=self.org_id,
            user_id=user_id,
            entity_type=entity_type,
            file_name=file_name[:255],
            file_path=saved_path,
            status="PENDING",
            total_rows=total_rows,
            processed_rows=0,
            successful_rows=0,
            failed_rows=0,
            duplicate_rows=0,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        return job, headers, samples, total_rows

    async def get_job(self, job_id: str) -> ImportJob:
        """Fetch import job with strict organization boundary check."""
        stmt = select(ImportJob).where(
            ImportJob.id == job_id,
            ImportJob.organization_id == self.org_id,
        )
        job = (await self.db.execute(stmt)).scalar_one_or_none()
        if not job:
            raise NotFoundException("Import job not found.")
        return job

    async def get_job_rows(
        self,
        job_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ImportRow]:
        """Fetch row-level error audit logs for an import job."""
        # Ensure job belongs to this tenant
        await self.get_job(job_id)

        stmt = select(ImportRow).where(ImportRow.import_job_id == job_id)
        if status:
            stmt = stmt.where(ImportRow.status == status.upper())
        stmt = stmt.order_by(ImportRow.row_number).limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def preview_import(
        self, job_id: str, mapping: Dict[str, str]
    ) -> ImportPreviewResponse:
        """Dry-run preview top sample rows with mapping and duplicate checks."""
        job = await self.get_job(job_id)
        headers, sample_rows, _ = get_headers_and_sample(job.file_path, sample_limit=10)

        preview_rows: List[ImportPreviewRow] = []
        for idx, raw in enumerate(sample_rows, start=1):
            mapped = self._apply_mapping(raw, mapping)
            is_valid, errors = self._validate_mapped_fields(job.entity_type, mapped)
            is_duplicate = False
            if is_valid:
                is_duplicate = await self._check_duplicate(job.entity_type, mapped)

            preview_rows.append(
                ImportPreviewRow(
                    row_number=idx,
                    raw=raw,
                    mapped=mapped,
                    is_valid=is_valid,
                    is_duplicate=is_duplicate,
                    validation_errors=errors,
                )
            )

        return ImportPreviewResponse(
            job_id=job.id,
            entity_type=job.entity_type,
            headers=headers,
            preview_rows=preview_rows,
            total_samples=len(preview_rows),
        )

    async def execute_import(self, job_id: str, mapping: Dict[str, str]) -> ImportJob:
        """Run batch ingestion with row validation, in-tenant duplicate detection, and row logging."""
        job = await self.get_job(job_id)
        if job.status == "PROCESSING":
            raise BadRequestException("Import job is already currently processing.")
        if job.status == "COMPLETED":
            raise BadRequestException("Cannot execute an import job that has already completed.")

        job.status = "PROCESSING"
        await self.db.commit()

        try:
            _, rows = read_all_rows(job.file_path)
            processed_count = 0
            success_count = 0
            fail_count = 0
            dup_count = 0

            for row_idx, raw_row in enumerate(rows, start=1):
                processed_count += 1
                mapped = self._apply_mapping(raw_row, mapping)
                is_valid, errors = self._validate_mapped_fields(job.entity_type, mapped)

                if not is_valid:
                    fail_count += 1
                    row_rec = ImportRow(
                        import_job_id=job.id,
                        row_number=row_idx,
                        raw_data=raw_row,
                        status="ERROR",
                        error_message="; ".join(errors),
                    )
                    self.db.add(row_rec)
                    continue

                # Check duplicate
                is_duplicate = await self._check_duplicate(job.entity_type, mapped)
                if is_duplicate:
                    dup_count += 1
                    row_rec = ImportRow(
                        import_job_id=job.id,
                        row_number=row_idx,
                        raw_data=raw_row,
                        status="DUPLICATE",
                        error_message=f"Duplicate {job.entity_type[:-1]} record detected in organization.",
                    )
                    self.db.add(row_rec)
                    continue

                # Ingest entity
                try:
                    await self._ingest_entity(job.entity_type, mapped)
                    success_count += 1
                    row_rec = ImportRow(
                        import_job_id=job.id,
                        row_number=row_idx,
                        raw_data=raw_row,
                        status="SUCCESS",
                    )
                    self.db.add(row_rec)
                except Exception as exc:
                    fail_count += 1
                    row_rec = ImportRow(
                        import_job_id=job.id,
                        row_number=row_idx,
                        raw_data=raw_row,
                        status="ERROR",
                        error_message=f"Database insertion error: {str(exc)}",
                    )
                    self.db.add(row_rec)

            job.total_rows = len(rows)
            job.processed_rows = processed_count
            job.successful_rows = success_count
            job.failed_rows = fail_count
            job.duplicate_rows = dup_count
            job.status = "COMPLETED"
            await self.db.commit()
            await self.db.refresh(job)
            return job

        except Exception as exc:
            logger.error(f"Fatal error executing import job {job.id}: {exc}", exc_info=True)
            job.status = "FAILED"
            job.errors = [{"fatal_error": str(exc)}]
            await self.db.commit()
            raise

    def _apply_mapping(self, raw: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        """Map raw file columns into normalized domain fields using user-provided mapping."""
        mapped = {}
        # If mapping provided, apply target keys
        if mapping:
            for file_col, target_field in mapping.items():
                if file_col in raw:
                    mapped[target_field] = str(raw[file_col]).strip() if raw[file_col] is not None else ""
        else:
            # Fallback direct normalization: lowercase underscored keys
            for k, v in raw.items():
                norm_key = k.strip().lower().replace(" ", "_")
                mapped[norm_key] = str(v).strip() if v is not None else ""
        return mapped

    def _validate_mapped_fields(
        self, entity_type: str, data: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Validate presence of required fields and proper data formatting."""
        errors: List[str] = []
        if entity_type == "leads":
            title = data.get("title") or data.get("contact_name") or data.get("name")
            if not title:
                errors.append("Missing required field: 'title' or 'contact_name'")
            email = data.get("email") or data.get("contact_email")
            if email and not EMAIL_REGEX.match(email):
                errors.append(f"Invalid email format: '{email}'")

        elif entity_type == "contacts":
            first_name = data.get("first_name") or data.get("name")
            if not first_name:
                errors.append("Missing required field: 'first_name' or 'name'")
            email = data.get("email")
            if email and not EMAIL_REGEX.match(email):
                errors.append(f"Invalid email format: '{email}'")

        elif entity_type == "companies":
            name = data.get("name") or data.get("company_name")
            if not name:
                errors.append("Missing required field: 'name'")

        return len(errors) == 0, errors

    async def _check_duplicate(self, entity_type: str, data: Dict[str, Any]) -> bool:
        """In-tenant duplicate check on email, phone, domain, or primary identifiers."""
        if entity_type == "leads":
            email = data.get("contact_email") or data.get("email")
            phone = data.get("contact_phone") or data.get("phone")
            title = data.get("title") or data.get("contact_name")

            if email:
                c_stmt = (
                    select(Contact.id)
                    .where(Contact.organization_id == self.org_id, Contact.email == email)
                    .limit(1)
                )
                if (await self.db.execute(c_stmt)).scalar_one_or_none():
                    return True

            if phone:
                c_stmt = (
                    select(Contact.id)
                    .where(Contact.organization_id == self.org_id, Contact.phone == phone)
                    .limit(1)
                )
                if (await self.db.execute(c_stmt)).scalar_one_or_none():
                    return True

            if title:
                l_stmt = (
                    select(Lead.id)
                    .where(Lead.organization_id == self.org_id, Lead.title == title)
                    .limit(1)
                )
                if (await self.db.execute(l_stmt)).scalar_one_or_none():
                    return True

        elif entity_type == "contacts":
            email = data.get("email")
            phone = data.get("phone")
            if email:
                stmt = select(Contact.id).where(
                    Contact.organization_id == self.org_id, Contact.email == email
                ).limit(1)
                if (await self.db.execute(stmt)).scalar_one_or_none():
                    return True
            if phone:
                stmt = select(Contact.id).where(
                    Contact.organization_id == self.org_id, Contact.phone == phone
                ).limit(1)
                if (await self.db.execute(stmt)).scalar_one_or_none():
                    return True

        elif entity_type == "companies":
            name = data.get("name") or data.get("company_name")
            domain = data.get("domain")
            if name:
                stmt = select(Company.id).where(
                    Company.organization_id == self.org_id,
                    func.lower(Company.name) == func.lower(name),
                ).limit(1)
                if (await self.db.execute(stmt)).scalar_one_or_none():
                    return True
            if domain:
                stmt = select(Company.id).where(
                    Company.organization_id == self.org_id, Company.domain == domain
                ).limit(1)
                if (await self.db.execute(stmt)).scalar_one_or_none():
                    return True

        return False

    async def _ingest_entity(self, entity_type: str, data: Dict[str, Any]) -> None:
        """Create entity in the database within current organization."""
        if entity_type == "leads":
            title = data.get("title") or data.get("contact_name") or data.get("name")
            contact_email = data.get("email") or data.get("contact_email")
            contact_phone = data.get("phone") or data.get("contact_phone")
            company_name = data.get("company") or data.get("company_name")
            source = data.get("source", "CSV Import")
            notes = data.get("notes")

            val_str = data.get("estimated_value") or data.get("value") or "0"
            try:
                est_value = float(re.sub(r"[^\d.]", "", str(val_str))) if val_str else 0.0
            except ValueError:
                est_value = 0.0

            # Optional linked contact
            contact_id = None
            if contact_email or data.get("contact_name"):
                c_name = data.get("contact_name") or title
                parts = c_name.strip().split(" ", 1)
                fn = parts[0]
                ln = parts[1] if len(parts) > 1 else ""
                contact = Contact(
                    organization_id=self.org_id,
                    first_name=fn,
                    last_name=ln or fn,
                    email=contact_email,
                    phone=contact_phone,
                    lead_source=source,
                )
                self.db.add(contact)
                await self.db.flush()
                contact_id = contact.id

            lead = Lead(
                organization_id=self.org_id,
                contact_id=contact_id,
                title=title,
                source=source,
                status=LeadStatus.NEW.value,
                priority=LeadPriority.MEDIUM.value,
                estimated_value=est_value,
                notes=notes,
            )
            self.db.add(lead)
            await self.db.flush()

        elif entity_type == "contacts":
            fn = data.get("first_name") or data.get("name")
            ln = data.get("last_name", "")
            if not ln and " " in fn:
                parts = fn.split(" ", 1)
                fn, ln = parts[0], parts[1]

            contact = Contact(
                organization_id=self.org_id,
                first_name=fn,
                last_name=ln or fn,
                email=data.get("email"),
                phone=data.get("phone"),
                title=data.get("title") or data.get("job_title"),
                lead_source=data.get("source", "CSV Import"),
                address=data.get("address"),
            )
            self.db.add(contact)
            await self.db.flush()

        elif entity_type == "companies":
            company = Company(
                organization_id=self.org_id,
                name=data.get("name") or data.get("company_name"),
                domain=data.get("domain"),
                industry=data.get("industry"),
                size=data.get("size"),
                phone=data.get("phone"),
                website=data.get("website"),
                address=data.get("address"),
                city=data.get("city"),
                country=data.get("country"),
            )
            self.db.add(company)
            await self.db.flush()
