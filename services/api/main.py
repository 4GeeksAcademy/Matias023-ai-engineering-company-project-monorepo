from pathlib import Path
import sys
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from database import init_db
from error_handlers import (
    incidents_validation_exception_handler,
    unhandled_exception_handler,
)
from models import HealthResponse, RootResponse
from routers.auth import router as auth_router
from routers.incidents import router as incidents_router
from routers.inventory import router as inventory_router
from routers.profiles import router as profiles_router
from routers.suppliers import router as suppliers_router
from routers.telemetry import router as telemetry_router
from routers.tasks import router as tasks_router
from routers.users import router as users_router
# `services.reporting` is a repository-root package while this API remains a
# flat setuptools project. Resolve the repository root independent of cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# Ensure the repository root is on sys.path before importing repository-root
# packages such as services.reporting.
from services.reporting.routers import router as reporting_router


# Load environment variables from .env before anything else
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create inventory tables when a DATABASE_URL is configured. This is a
    # no-op on the in-memory engine when DATABASE_URL is unset, so existing
    # behaviour (TinyDB-only) is preserved.
    init_db()
    yield


app = FastAPI(
    title="TrackFlow Supplier Directory API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_exception_handler(RequestValidationError,
                          incidents_validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


app.include_router(users_router)
app.include_router(profiles_router)
app.include_router(auth_router)
app.include_router(suppliers_router)
app.include_router(inventory_router)
app.include_router(telemetry_router, prefix="/telemetry")
app.include_router(tasks_router, prefix="/tasks")
app.include_router(reporting_router)

# Canonical, documented route.
app.include_router(incidents_router, prefix="/api/incidents")
# Compatibility alias for the existing Vite dev proxy (/api/* -> /*).
# Same router/handlers, no duplicated logic — hidden from the OpenAPI
# schema to avoid showing every operation twice.
app.include_router(incidents_router, prefix="/incidents",
                   include_in_schema=False)


@app.get("/", response_model=RootResponse)
def root():
    return {
        "message": "TrackFlow Supplier Directory API",
        "status": "ok",
    }


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}
