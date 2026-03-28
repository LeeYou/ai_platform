"""FastAPI application entrypoint for the Training Management backend."""

import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from database import Base, engine
from routers import capabilities, datasets, jobs, models, ws

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_DIR = os.getenv("LOG_DIR", "/workspace/logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def _setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "train.log"),
        maxBytes=50 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    return logging.getLogger("train")


logger = _setup_logging()

# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("./data/logs", exist_ok=True)
    os.makedirs("./data/models", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info("Train Management service started")
    yield
    logger.info("Train Management service stopped")


app = FastAPI(
    title="Train Management API",
    version="1.0.0",
    description="Backend for AI model training, monitoring and model package export",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
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
    logger.warning("Validation error on %s %s — %s", request.method, request.url.path, detail)
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path, exc, traceback.format_exc(),
    )
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请查看日志排查原因"})


app.include_router(capabilities.router)
app.include_router(datasets.router)
app.include_router(jobs.router)
app.include_router(models.router)
app.include_router(ws.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
