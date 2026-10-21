from contextlib import asynccontextmanager
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import check_db_health, engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import logger
from app.core.redis import check_redis_health, close_redis, get_redis_pool
import app.models  # Ensure all SQLAlchemy models are registered
from app.modules.activities.router import router as activities_router
from app.modules.ai.factory import get_ai_provider
from app.modules.ai.router import router as ai_router
from app.modules.auth.router import router as auth_router
from app.modules.automation.router import router as automation_router
import app.modules.automation.workflows  # Ensure event subscribers are loaded and registered
from app.modules.calendar.router import router as calendar_router
from app.modules.companies.router import router as companies_router
from app.modules.contacts.router import router as contacts_router
from app.modules.deals.router import router as deals_router
from app.modules.imports.router import router as imports_router
from app.modules.leads.router import router as leads_router
from app.modules.notifications.router import router as notifications_router
from app.modules.organizations.router import router as organizations_router
from app.modules.pipelines.router import router as pipelines_router
from app.modules.reports.router import router as reports_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode...")
    # Initialize redis pool if available
    try:
        await get_redis_pool()
    except Exception as e:
        logger.warning(f"Redis initialization notice: {e}")

    # Register CRM built-in operational event workflows
    from app.modules.automation.workflows import register_standard_workflows
    register_standard_workflows()

    # Log active AI provider
    ai_provider = get_ai_provider()
    logger.info(f"AI Intelligence initialized with provider: '{ai_provider.provider_name}'")

    yield

    logger.info("Shutting down NexusCRM backend...")
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="NexusCRM API",
    description="Intelligent Customer Relationship Management platform API for small and growing businesses.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register uniform error handlers
register_exception_handlers(app)


# Structured Request / Response Middleware
@app.middleware("http")
async def logging_and_timing_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.time()

    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{process_time:.2f}ms"

    if not request.url.path.startswith("/health"):
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({process_time:.2f}ms)",
            extra={"request_id": request_id},
        )
    return response


# Health Check Endpoints
@app.get("/health", tags=["Health & Diagnostics"])
async def root_health():
    """General API liveness health check."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "version": "1.0.0",
    }


@app.get("/health/db", tags=["Health & Diagnostics"])
async def db_health():
    """Database connectivity health check."""
    db_ok = await check_db_health()
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected",
    }


@app.get("/health/redis", tags=["Health & Diagnostics"])
async def redis_health():
    """Redis cache and queue health check."""
    redis_ok = await check_redis_health()
    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis": "connected" if redis_ok else "disconnected/in-memory fallback",
    }


@app.get("/health/ai", tags=["Health & Diagnostics"])
async def ai_health():
    """AI intelligence layer health check."""
    ai_provider = get_ai_provider()
    return {
        "status": "operational",
        "provider": ai_provider.provider_name,
        "is_mock": (ai_provider.provider_name == "mock"),
        "available": ai_provider.is_available,
    }


# Mount all API V1 Domain Routers using APIRouter for unified dependency resolution & OpenAPI schema
from fastapi import APIRouter

api_v1_router = APIRouter(prefix=settings.API_V1_PREFIX)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(organizations_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(leads_router)
api_v1_router.include_router(contacts_router)
api_v1_router.include_router(companies_router)
api_v1_router.include_router(pipelines_router)
api_v1_router.include_router(deals_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(activities_router)
api_v1_router.include_router(calendar_router)
api_v1_router.include_router(automation_router)
api_v1_router.include_router(imports_router)
api_v1_router.include_router(ai_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(reports_router)

app.include_router(api_v1_router)
