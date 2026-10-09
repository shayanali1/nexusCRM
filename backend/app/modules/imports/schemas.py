"""Pydantic schemas for Batch Ingestion Pipeline (CSV/XLSX)."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ImportUploadResponse(BaseModel):
    job_id: str
    file_name: str
    entity_type: str
    status: str
    detected_headers: List[str]
    sample_rows: List[Dict[str, Any]]
    total_rows_estimated: int


class ImportPreviewRequest(BaseModel):
    mapping: Optional[Dict[str, str]] = Field(default_factory=dict)


class ImportPreviewRow(BaseModel):
    row_number: int
    raw: Dict[str, Any]
    mapped: Dict[str, Any]
    is_valid: bool
    is_duplicate: bool
    validation_errors: List[str] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    job_id: str
    entity_type: str
    headers: List[str]
    preview_rows: List[ImportPreviewRow]
    total_samples: int


class ImportExecuteRequest(BaseModel):
    mapping: Dict[str, str] = Field(
        ...,
        description="Dictionary mapping CSV headers to entity fields (e.g. {'Email Address': 'email'})",
    )
    background: bool = Field(False, description="Whether to enqueue processing via Celery background worker")


class ImportJobResponse(BaseModel):
    id: str
    entity_type: str
    file_name: str
    status: str
    total_rows: int
    processed_rows: int
    successful_rows: int
    failed_rows: int
    duplicate_rows: int
    errors: List[Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImportRowResponse(BaseModel):
    id: str
    import_job_id: str
    row_number: int
    status: str  # SUCCESS, ERROR, DUPLICATE, PENDING
    raw_data: Dict[str, Any]
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
