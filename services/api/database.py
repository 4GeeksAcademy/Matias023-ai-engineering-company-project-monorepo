import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine
from tinydb import TinyDB


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "suppliers.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)

db = TinyDB(DB_PATH)
suppliers_table = db.table("suppliers")
users_table = db.table("users")
profiles_table = db.table("profiles")
reset_tokens_table = db.table("reset_tokens")
incidents_table = db.table("incidents")

# Internal-only table: maps historical seed dedup keys to the TinyDB
# doc_id of the incident they created. Never exposed via the API.
incident_seed_keys_table = db.table("incident_seed_keys")


def document_to_dict(document):
    return {
        "id": document.doc_id,
        **dict(document),
    }


# ──────────────────────────────────────────────
# Inventory: SQLModel / relational database
# ──────────────────────────────────────────────
#
# The API is a dual-database service:
#   * TinyDB  -> users, profiles, suppliers, incidents (existing, unchanged)
#   * SQLModel -> inventory (SKU, StockEntry, StockExit) on PostgreSQL /
#                 Supabase, configured via DATABASE_URL.
#
# The engine is built lazily so that importing this module never fails and
# legacy tests / tooling that never set DATABASE_URL keep working unchanged.

_engine = None
_engine_url = None


def _get_database_url() -> str:
    """Return the configured DATABASE_URL, read at call time.

    Read from ``os.environ`` on every call rather than caching at import time:
    ``main.py`` calls ``load_dotenv()`` after this module is imported, so a
    ``DATABASE_URL`` supplied through ``services/api/.env`` is only visible
    to the engine if we resolve it lazily when the engine is actually built.
    """
    return os.environ.get("DATABASE_URL", "").strip()


def _resolve_engine_url(sqlite_default: str | None = None) -> str:
    """Return the DATABASE_URL to use for the engine.

    Priority:
      1. DATABASE_URL environment variable (read at call time -> sees .env).
      2. sqlite_default parameter (used by tests to force an in-memory DB).
    Falls back to an in-memory SQLite ONLY when the caller explicitly asked
    for/permits a local fallback. In a production-like environment
    (APP_ENV=production) a missing DATABASE_URL fails loudly instead of
    silently running on an ephemeral database.
    """
    database_url = _get_database_url()

    if database_url:
        return database_url

    if sqlite_default:
        return sqlite_default

    # Local development is allowed to run on a throwaway SQLite database,
    # but ONLY when the operator explicitly opts in. Without that flag (and
    # with no DATABASE_URL), a production-like start must not silently
    # persist to an in-memory database that vanishes on restart.
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    allow_sqlite_fallback = os.environ.get(
        "ALLOW_SQLITE_FALLBACK", ""
    ).strip().lower() in {"1", "true", "yes", "on"}

    if app_env == "production" and not allow_sqlite_fallback:
        raise RuntimeError(
            "DATABASE_URL is required in a production environment but was not "
            "set. Configure DATABASE_URL (e.g. Supabase/PostgreSQL) before "
            "starting the API. To run locally on SQLite, set "
            "APP_ENV=development or ALLOW_SQLITE_FALLBACK=1 explicitly."
        )

    return "sqlite://"


def get_engine(sqlite_default: str | None = None):
    """Create (once) and return the SQL/Alchemy engine.

    The engine URL is resolved lazily so tests can inject a sqlite_default
    even when DATABASE_URL is unset at import time, and so a DATABASE_URL
    loaded via load_dotenv() later is picked up. In a production environment
    (APP_ENV=production) without DATABASE_URL, raises instead of silently
    falling back to SQLite.
    """
    global _engine, _engine_url

    resolved_url = _resolve_engine_url(sqlite_default)

    if _engine is None or _engine_url != resolved_url:
        kwargs = {"pool_pre_ping": True}
        if resolved_url.startswith("sqlite"):
            # check_same_thread=False is required for FastAPI/TestClient
            # usage where the engine is shared across threads.
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(resolved_url, **kwargs)
        _engine_url = resolved_url

    return _engine


def reset_engine_for_tests() -> None:
    """Drop the cached engine. Used by tests to switch DB targets."""
    global _engine, _engine_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None


def get_db():
    """FastAPI dependency yielding a SQLModel session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


def init_db() -> None:
    """Create inventory tables. Safe to call repeatedly.

    When DATABASE_URL is unset and SQLite fallback is permitted (local
    development), tables are created on the in-memory engine. In a
    production environment without DATABASE_URL this raises rather than
    silently using an ephemeral database; persistence then requires the
    operator to configure DATABASE_URL.
    """
    # Import explicitly so the ORM models are registered with
    # SQLModel.metadata before create_all().  The calling module may not
    # have imported inventory_models (e.g. when init_db is called from a
    # standalone script or test), and SQLModel only discovers tables from
    # classes that have actually been imported.
    import inventory_models  # noqa: F401  register SKU, StockEntry, StockExit
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
