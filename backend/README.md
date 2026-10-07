# NexusCRM — Backend (FastAPI + PostgreSQL + Celery + Mock AI)

The backend for **NexusCRM** is a production-ready, modular monolith written in Python with FastAPI, SQLAlchemy 2.0, Alembic, Celery, and Redis. It enforces multi-tenant organization boundaries, fine-grained role-based access control (RBAC), and features a **provider-agnostic AI layer that works out of the box with zero external API keys (`AI_PROVIDER=mock`)**.

---

## 1. Key Architectural Principles

1. **Strict Multi-Tenancy**: The top-level boundary is `Organization`. Every tenant-scoped table inherits `TenantMixin` (`organization_id`). Tenant isolation is strictly enforced at the database and dependency layer—never trusting client-supplied IDs.
2. **Provider-Agnostic AI Layer**: Abstract base class `AIProvider` with a built-in `MockAIProvider` as the default. Real providers (OpenAI, Gemini, Anthropic) can be enabled via `.env` without modifying CRM business logic.
3. **Async Background Jobs**: Non-blocking Celery worker queue for background AI inference, automation rule evaluation, and batch CSV imports.
4. **Domain-Based Modules**: Each domain (`auth`, `organizations`, `users`, `leads`, `contacts`, `companies`, `pipelines`, `deals`, `tasks`, `activities`, `automation`, `ai`, `reports`, `notifications`) contains dedicated `models.py`, `schemas.py`, `repository.py`, and `router.py`.

---

## 2. Directory Structure

```text
backend/
├── app/
│   ├── main.py                    # FastAPI entrypoint, middleware, diagnostics & routing
│   ├── db_init.py                 # Standalone table initialization & seeder
│   ├── core/
│   │   ├── config.py              # Pydantic BaseSettings (.env configuration)
│   │   ├── database.py            # SQLAlchemy 2.0 async engine & session dependency
│   │   ├── exceptions.py          # App exceptions & standardized JSON error handlers
│   │   ├── logging.py             # Structured logging with request ID tracking
│   │   ├── permissions.py         # RBAC role-to-permission mapping
│   │   ├── redis.py               # Async Redis connection & health check
│   │   └── security.py            # Bcrypt hashing & JWT issuance
│   ├── models/
│   │   └── __init__.py            # Aggregated model registry for Alembic reflection
│   ├── modules/
│   │   ├── auth/                  # Register, Login, Refresh, Me
│   │   ├── organizations/         # Multi-tenant workspace management
│   │   ├── users/                 # Team members & user roles
│   │   ├── leads/                 # Lead lifecycle & conversion to Deals
│   │   ├── contacts/              # Customer contacts directory
│   │   ├── companies/             # Business accounts
│   │   ├── pipelines/             # Pipelines & stage order management
│   │   ├── deals/                 # Sales deals & stage movement
│   │   ├── tasks/                 # Follow-ups (overdue, due today, upcoming)
│   │   ├── activities/            # Chronological customer timeline logging
│   │   ├── automation/            # Event-Condition-Action automation engine
│   │   ├── ai/                    # AIProvider interface, MockAI, OpenAI, caching
│   │   ├── notifications/         # User in-app notifications
│   │   ├── reports/               # Executive dashboard KPIs & rep leaderboard
│   │   ├── calendar/              # Calendar events & external sync
│   │   ├── imports/               # CSV/XLSX batch ingestion models
│   │   ├── integrations/          # Third-party integrations
│   │   └── audit/                 # Security audit logs
│   ├── workers/
│   │   ├── celery_app.py          # Celery configuration
│   │   ├── ai_jobs.py             # Background AI tasks
│   │   ├── automation_jobs.py     # Background automation dispatcher
│   │   └── import_jobs.py         # Background import processing
│   └── seed/
│       └── seed_data.py           # Realistic demo dataset seeder
├── alembic/
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│       └── 001_initial_schema.py
├── tests/
│   ├── conftest.py                # In-memory test engine & auth fixtures
│   ├── test_auth.py               # Auth & registration tests
│   ├── test_tenant_isolation.py   # Strict multi-tenancy verification tests
│   ├── test_permissions.py        # RBAC role permission checks
│   ├── test_ai_provider.py        # Mock AI layer tests
│   └── test_leads_and_deals.py    # Lead lifecycle and Deal conversion tests
├── requirements.txt
├── Dockerfile
└── .env.example
```

---

## 3. Database Schema & Entities

| Model | Table | Purpose |
| :--- | :--- | :--- |
| `Organization` | `organizations` | Root tenant boundary (slug, settings, plan) |
| `User` | `users` | Authenticated team members with RBAC (`OWNER`, `ADMIN`, `MANAGER`, `MEMBER`) |
| `Company` | `companies` | Business accounts (domain, size, industry, city) |
| `Contact` | `contacts` | Individual customer contacts |
| `Pipeline` & `PipelineStage` | `pipelines`, `pipeline_stages` | Customizable sales stages with win probabilities |
| `Lead` | `leads` | Inbound prospects (*New → Contacted → Qualified → Interested → Proposal → Negotiation → Won/Lost*) |
| `Deal` | `deals` | Pipeline opportunities with revenue forecasting and stage moves |
| `Activity` | `activities` | Chronological interaction stream (calls, emails, meetings, proposals, notes) |
| `Task` | `tasks` | Explicit follow-ups with overdue detection and 1-click completion |
| `CalendarEvent` | `calendar_events` | Scheduled meetings and sync adapters |
| `AutomationRule` & `Action` | `automation_rules`, `automation_actions` | Event-driven automation workflows |
| `AIInsight` & `AIJob` | `ai_insights`, `ai_jobs` | Cached AI outputs and asynchronous task tracking |
| `Notification` | `notifications` | In-app alerts |
| `ImportJob` & `ImportRow` | `import_jobs`, `import_rows` | CSV/XLSX validation and ingestion logs |
| `Integration` & `AuditLog` | `integrations`, `audit_logs` | Third-party configurations and security audit trail |

---

## 4. API Endpoints Summary (`/api/v1`)

### Health & Diagnostics
* `GET /health` — API service liveness
* `GET /health/db` — PostgreSQL connectivity check
* `GET /health/redis` — Redis status check
* `GET /health/ai` — AI provider runtime status

### Authentication & Tenant Scoping (`/api/v1/auth`)
* `POST /api/v1/auth/register` — Register new organization + Owner account + default pipeline
* `POST /api/v1/auth/login` — Authenticate and obtain JWT access & refresh tokens
* `POST /api/v1/auth/refresh` — Issue fresh access token using refresh token
* `GET /api/v1/auth/me` — Return current user profile and tenant details

### CRM Operations
* `GET|POST /api/v1/leads` — List and create leads
* `GET|PATCH|DELETE /api/v1/leads/{id}` — Lead detail, update, delete
* `POST /api/v1/leads/{id}/convert` — Convert qualified lead to Deal + Customer record
* `GET|POST /api/v1/contacts` — Contact directory CRUD
* `GET|POST /api/v1/companies` — Company accounts CRUD
* `GET|POST /api/v1/deals` — Sales deals CRUD
* `POST /api/v1/deals/{id}/move-stage` — Move deal stage on Kanban pipeline
* `GET|POST /api/v1/pipelines` — Manage pipelines and stages
* `GET|POST /api/v1/tasks` — List tasks with overdue / due today / upcoming filters
* `POST /api/v1/tasks/{id}/complete` — 1-click follow-up completion
* `GET|POST /api/v1/activities` — Chronological customer timeline logging
* `GET|POST|PATCH /api/v1/automation/rules` — Workflow automation rules
* `GET /api/v1/reports/dashboard` — Management overview (KPIs, stage distribution, rep leaderboard)

### AI Intelligence Layer (`/api/v1/ai`)
* `GET /api/v1/ai/status` — Returns active AI provider (`mock` or configured LLM)
* `POST /api/v1/ai/summary` — Generates 2-3 sentence customer history summary
* `POST /api/v1/ai/prioritize` — Calculates explainable lead priority score with clear reasons
* `POST /api/v1/ai/next-action` — Recommends actionable next sales steps
* `POST /api/v1/ai/draft-message` — Context-aware email / WhatsApp follow-up drafter
* `POST /api/v1/ai/deal-guidance` — Analyzes deal velocity, risk factors, and tactics

---

## 5. Running the Application

### Option A: Running with Docker Compose (Recommended)

From the project root:

```bash
docker compose up --build
```

Services started:
* **Backend API**: `http://localhost:8000` (Swagger UI at `http://localhost:8000/docs`)
* **PostgreSQL**: `localhost:5432`
* **Redis**: `localhost:6379`
* **Celery Worker**: Background task executor
* **MinIO Storage**: `http://localhost:9000` (Console at `http://localhost:9001`)

### Option B: Local Python Development

1. Create and activate a Python virtual environment:
   ```bash
   python -m venv backend/venv
   .\backend\venv\Scripts\Activate.ps1   # Windows
   source backend/venv/bin/activate      # Linux/macOS
   ```

2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

3. Initialize database tables and seed demo dataset:
   ```bash
   python backend/app/db_init.py
   ```

4. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
   ```

---

## 6. Running Automated Tests

Run the complete pytest test suite:

```bash
pytest backend/tests -v
```

All 12 unit and integration tests verify:
* Organization registration & JWT authentication
* Strict multi-tenant isolation across organizations
* Role-based permissions enforcement (RBAC)
* Zero-cost Mock AI Provider intelligence operations
* Lead lifecycle progression & Deal conversion
