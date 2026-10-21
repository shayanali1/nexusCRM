from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.core.logging import logger


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            details=details,
        )


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Authentication required", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            details=details,
        )


class ForbiddenException(AppException):
    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            details=details,
        )


class TenantIsolationException(AppException):
    def __init__(self, message: str = "Access to foreign organization resource is strictly forbidden"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code="TENANT_ISOLATION_VIOLATION",
        )


class BadRequestException(AppException):
    def __init__(self, message: str = "Invalid request", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            details=details,
        )


class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            code="CONFLICT",
            details=details,
        )


class AIProviderException(AppException):
    """Graceful exception for AI provider outages or failures."""

    def __init__(self, message: str = "AI service is currently unavailable", provider: str = "unknown"):
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AI_PROVIDER_UNAVAILABLE",
            details={"provider": provider, "fallback_mode": True},
        )


def _sanitize_validation_errors(raw_errors: Any) -> Any:
    """Sanitize sensitive input fields (e.g. body.credentials) from validation errors."""
    if not isinstance(raw_errors, list):
        return raw_errors

    sanitized = []
    for err in raw_errors:
        if isinstance(err, dict):
            err_copy = dict(err)
            loc = err_copy.get("loc", ())
            # Narrowly target credentials field errors (e.g. ('body', 'credentials'))
            if any(str(part).lower() == "credentials" for part in loc):
                if "input" in err_copy:
                    err_copy["input"] = "[REDACTED]"
                if "ctx" in err_copy and isinstance(err_copy["ctx"], dict):
                    ctx_copy = dict(err_copy["ctx"])
                    for k in ("error", "input"):
                        if k in ctx_copy:
                            ctx_copy[k] = "[REDACTED]"
                    err_copy["ctx"] = ctx_copy
            sanitized.append(err_copy)
        else:
            sanitized.append(err)
    return sanitized


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform JSON exception handlers for the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.warning(
            f"AppException: {exc.code} - {exc.message} on {request.method} {request.url.path}",
            extra={"details": exc.details},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        sanitized_details = _sanitize_validation_errors(jsonable_encoder(exc.errors()))
        logger.info(f"Validation error on {request.method} {request.url.path}: {sanitized_details}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": sanitized_details,
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred.",
                },
            },
        )
