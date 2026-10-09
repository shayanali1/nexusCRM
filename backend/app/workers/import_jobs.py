from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.modules.imports.service import ImportService
from app.workers.celery_app import celery_app, run_async_in_worker


async def async_process_csv_import(
    import_job_id: str,
    organization_id: str,
    mapping: Optional[Dict[str, str]] = None,
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Underlying async implementation of CSV/XLSX import job execution."""
    async def _execute(db: AsyncSession):
        service = ImportService(db, organization_id)
        job = await service.execute_import(import_job_id, mapping or {})
        return {
            "import_job_id": job.id,
            "status": job.status,
            "total_rows": job.total_rows,
            "successful_rows": job.successful_rows,
            "failed_rows": job.failed_rows,
            "duplicate_rows": job.duplicate_rows,
        }

    if session:
        return await _execute(session)
    else:
        async with AsyncSessionLocal() as db:
            return await _execute(db)


@celery_app.task(
    name="app.workers.import_jobs.process_csv_import",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_csv_import(
    import_job_id: str,
    organization_id: str,
    mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Process background batch CSV/XLSX file ingestion with isolated async DB session."""
    logger.info(f"Processing background CSV import {import_job_id} for org {organization_id}")
    return run_async_in_worker(
        async_process_csv_import(import_job_id, organization_id, mapping)
    )
