"""REST API Router for Batch Ingestion Pipeline (CSV/XLSX)."""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import BadRequestException
from app.core.logging import logger
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.imports.schemas import (
    ImportExecuteRequest,
    ImportJobResponse,
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportRowResponse,
    ImportUploadResponse,
)
from app.modules.imports.service import ImportService
from app.modules.users.models import User

router = APIRouter(prefix="/imports", tags=["Data Import (CSV / Excel)"])


@router.post("/upload", response_model=ImportUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_import_file(
    file: UploadFile = File(...),
    entity_type: str = Form("leads", description="leads, contacts, or companies"),
    current_user: User = Depends(require_permission(Permission.LEADS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV or Excel (.xlsx) file for batch ingestion."""
    if not file.filename:
        raise BadRequestException("No file uploaded.")

    content = await file.read()
    service = ImportService(db, current_user.organization_id)
    job, headers, sample_rows, total_rows = await service.create_upload_job(
        user_id=current_user.id,
        file_name=file.filename,
        file_content=content,
        entity_type=entity_type.lower(),
    )

    return ImportUploadResponse(
        job_id=job.id,
        file_name=job.file_name,
        entity_type=job.entity_type,
        status=job.status,
        detected_headers=headers,
        sample_rows=sample_rows,
        total_rows_estimated=total_rows,
    )


@router.post("/{job_id}/preview", response_model=ImportPreviewResponse)
async def preview_import(
    job_id: str,
    req: ImportPreviewRequest,
    current_user: User = Depends(require_permission(Permission.LEADS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Dry-run preview top sample rows with mapping and duplicate checks."""
    service = ImportService(db, current_user.organization_id)
    return await service.preview_import(job_id, req.mapping or {})


@router.post("/{job_id}/execute", response_model=ImportJobResponse)
async def execute_import(
    job_id: str,
    req: ImportExecuteRequest,
    current_user: User = Depends(require_permission(Permission.LEADS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Execute batch import with validation, duplicate detection, and row logging."""
    service = ImportService(db, current_user.organization_id)

    if req.background:
        job = await service.get_job(job_id)
        if job.status == "PROCESSING":
            raise BadRequestException("Import job is already currently processing.")
        if job.status == "COMPLETED":
            raise BadRequestException("Cannot execute an import job that has already completed.")
        try:
            from app.workers.import_jobs import process_csv_import
            process_csv_import.delay(job_id, current_user.organization_id, req.mapping)
            return job
        except Exception as exc:
            logger.warning(f"Background worker unavailable ({exc}), running synchronously")

    job = await service.execute_import(job_id, req.mapping)
    return job


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import_status(
    job_id: str,
    current_user: User = Depends(require_permission(Permission.LEADS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get the current progress status and metrics of an import job."""
    service = ImportService(db, current_user.organization_id)
    return await service.get_job(job_id)


@router.get("/{job_id}/rows", response_model=List[ImportRowResponse])
async def get_import_row_audit(
    job_id: str,
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, ERROR, DUPLICATE)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.LEADS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve row-by-row import outcome and validation error audit logs."""
    service = ImportService(db, current_user.organization_id)
    rows = await service.get_job_rows(job_id, status=status, limit=limit, offset=offset)
    return rows
