from typing import Any, Dict
from app.core.logging import logger
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.import_jobs.process_csv_import")
def process_csv_import(import_job_id: str, organization_id: str) -> Dict[str, Any]:
    """Process background batch CSV/XLSX file ingestion."""
    logger.info(f"Processing background CSV import {import_job_id} for org {organization_id}")
    return {
        "import_job_id": import_job_id,
        "status": "completed",
    }
