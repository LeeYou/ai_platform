"""FastAPI application entrypoint for the License Management backend."""

import hmac
import logging
import os
import sys
import time
import traceback
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

# ---------------------------------------------------------------------------
# Logging setup — MUST run before any third-party / app imports so that
# import errors are captured in the log file.
# ---------------------------------------------------------------------------

LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ADMIN_TOKEN = os.getenv("AI_ADMIN_TOKEN", "changeme").strip()


def _parse_allowed_origins() -> list[str]:
    raw = os.getenv(
        "AI_ALLOWED_ORIGINS",
        "http://localhost,http://127.0.0.1,http://localhost:5173,http://127.0.0.1:5173",
    ).strip()
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


ALLOWED_ORIGINS = _parse_allowed_origins()


def _setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "license.log"),
        maxBytes=50 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    # Use a named logger (not root) so uvicorn's dictConfig() cannot
    # remove our handlers when it reconfigures the root logger.
    app_logger = logging.getLogger("license")
    app_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.propagate = False

    return app_logger


logger = _setup_logging()
logger.info("=== Logging initialized — log_dir=%s, level=%s ===", LOG_DIR, LOG_LEVEL)

# ---------------------------------------------------------------------------
# Third-party & application imports (any error will now appear in the log)
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    from database import Base, engine
    from key_store import ensure_private_keys_dir
    from routers import capabilities, customers, keys, licenses, prod_tokens
except Exception:
    logger.critical("Failed to import application modules:\n%s", traceback.format_exc())
    sys.exit(1)

# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------


def _run_migrations(eng) -> None:
    """Add columns that may be missing from an older SQLite schema.

    ``create_all()`` only creates *new* tables — it never alters existing ones.
    We therefore check for columns introduced after the initial release and
    ``ALTER TABLE … ADD COLUMN`` when necessary.
    """
    import sqlalchemy

    inspector = sqlalchemy.inspect(eng)
    if "license_records" not in inspector.get_table_names():
        return  # fresh install — create_all() already handled everything

    with eng.connect() as conn:
        cols = {c["name"] for c in inspector.get_columns("license_records")}

        if "key_pair_id" not in cols:
            logger.info("Migrating: adding key_pair_id column to license_records")
            conn.execute(
                sqlalchemy.text(
                    "ALTER TABLE license_records ADD COLUMN key_pair_id INTEGER"
                    " REFERENCES key_pairs(id)"
                )
            )
            conn.commit()
            logger.info("Migration complete: key_pair_id added")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("./data/licenses", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _run_migrations(engine)
    ensure_private_keys_dir()
    logger.info("License Management service started")
    yield
    logger.info("License Management service stopped")


app = FastAPI(
    title="License Management API",
    version="1.0.0",
    description="Backend for issuing, renewing, and revoking AI platform licenses",
    lifespan=lifespan,
)

# CORS — open for all origins in dev mode
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

def _extract_admin_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("X-Admin-Token", "").strip()


def _requires_admin_auth(request: Request) -> bool:
    return request.url.path.startswith("/api/v1/") and request.method not in {"GET", "HEAD", "OPTIONS"}


def _enforce_admin_auth(request: Request):
    token = _extract_admin_token(request)
    if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return None


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        if _requires_admin_auth(request):
            auth_error = _enforce_admin_auth(request)
            if auth_error is not None:
                return auth_error
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s → %s (%.0fms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
        return response
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "%s %s → 500 (%.0fms) %s: %s\n%s",
            request.method, request.url.path, elapsed_ms,
            type(exc).__name__, exc, traceback.format_exc(),
        )
        raise


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for e in exc.errors():
        field = e["loc"][-1] if e.get("loc") else "unknown"
        errors.append(f"{field}: {e['msg']}")
    detail = "; ".join(errors)
    logger.warning(
        "Validation error on %s %s — %s",
        request.method, request.url.path, detail,
    )
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path, exc, traceback.format_exc(),
    )
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请查看日志排查原因"})


# API routers
app.include_router(capabilities.router)
app.include_router(customers.router)
app.include_router(licenses.router)
app.include_router(keys.router)
app.include_router(prod_tokens.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


# Serve built frontend if it exists
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
