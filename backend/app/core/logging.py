import logging
import sys
from typing import Any, Dict
from app.core.config import settings


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured console & file logs."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        log_data: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "organization_id"):
            log_data["organization_id"] = record.organization_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if settings.APP_DEBUG:
            extra_info = ""
            if "request_id" in log_data:
                extra_info += f" [req:{log_data['request_id']}]"
            if "organization_id" in log_data:
                extra_info += f" [org:{log_data['organization_id']}]"
            return f"[{timestamp}] {record.levelname:<7} {record.name}{extra_info}: {record.getMessage()}"

        import json
        return json.dumps(log_data)


def setup_logging() -> logging.Logger:
    """Configure root and application loggers."""
    log_level = logging.DEBUG if settings.APP_DEBUG else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter(datefmt="%Y-%m-%d %H:%M:%S"))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers = [handler]

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger("nexuscrm")
    logger.setLevel(log_level)
    return logger


logger = setup_logging()
