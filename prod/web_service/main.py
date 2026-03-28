"""Production REST API service — Layer 1 HTTP service.

Serves AI inference requests, exposes health/capabilities/license/reload APIs.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Logging setup — MUST run before any third-party / app imports so that
# import errors are captured in the log file.
# ---------------------------------------------------------------------------

LOG_DIR = os.getenv("LOG_DIR", "/mnt/ai_platform/logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()


def _setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "prod.log"),
        maxBytes=50 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    app_logger = logging.getLogger("prod")
    app_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.propagate = False

    return app_logger


logger = _setup_logging()
logger.info("=== Logging initialized — log_dir=%s, level=%s ===", LOG_DIR, LOG_LEVEL)

# ---------------------------------------------------------------------------
# Third-party & application imports
# ---------------------------------------------------------------------------
try:
    import numpy as np
    from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel

    from inference_engine import ProdInferenceEngine
    from resource_resolver import (
        LICENSE_PATH,
        list_available_capabilities,
        resolve_model_dir,
    )
except Exception:
    logger.critical("Failed to import application modules:\n%s", traceback.format_exc())
    sys.exit(1)

# ---------------------------------------------------------------------------
# Admin token (simple bearer auth for reload endpoint)
# ---------------------------------------------------------------------------

ADMIN_TOKEN = os.getenv("AI_ADMIN_TOKEN", "changeme")

# ---------------------------------------------------------------------------
# Capability engine registry
# ---------------------------------------------------------------------------

_engines: dict[str, ProdInferenceEngine] = {}


def _load_engines() -> None:
    caps = list_available_capabilities()
    for cap_info in caps:
        cap  = cap_info["capability"]
        mdir = cap_info["model_dir"]
        try:
            _engines[cap] = ProdInferenceEngine(cap, mdir)
            logger.info("Loaded capability: %s v%s from %s", cap, _engines[cap].version, mdir)
        except Exception as exc:
            logger.error("Failed to load %s: %s", cap, exc)


# ---------------------------------------------------------------------------
# License status helper
# ---------------------------------------------------------------------------

def _license_status() -> dict:
    if not os.path.exists(LICENSE_PATH):
        return {
            "status":         "missing",
            "license_id":     None,
            "valid_until":    None,
            "days_remaining": 0,
            "capabilities":   [],
        }
    try:
        with open(LICENSE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "status":         data.get("status", "unknown"),
            "license_id":     data.get("license_id"),
            "valid_until":    data.get("valid_until"),
            "days_remaining": data.get("days_remaining", 0),
            "capabilities":   data.get("capabilities", []),
        }
    except Exception as exc:
        logger.error("Failed to parse license file %s: %s", LICENSE_PATH, exc)
        return {"status": "invalid", "license_id": None, "valid_until": None,
                "days_remaining": 0, "capabilities": []}


def _check_license(capability: str) -> None:
    lic = _license_status()
    if lic["status"] == "missing":
        # Dev/test mode — no license file present, allow all
        return
    if lic["status"] == "expired":
        raise HTTPException(status_code=403,
                            detail={"code": 4002, "message": "License expired",
                                    "capability": capability})
    if lic["status"] not in ("active", "valid"):
        raise HTTPException(status_code=403,
                            detail={"code": 4001, "message": "License invalid",
                                    "capability": capability})
    if capability not in lic.get("capabilities", []):
        raise HTTPException(status_code=403,
                            detail={"code": 4004, "message": "Capability not licensed",
                                    "capability": capability})


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_engines()
    logger.info("Production AI service started — %d capabilities loaded", len(_engines))
    yield
    logger.info("Production AI service stopped")


app = FastAPI(
    title="AI Production Service",
    version="1.0.0",
    description=(
        "Agile Star AI Production REST API — "
        "面向客户的 AI 推理服务，支持多能力、热重载、License 校验"
    ),
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
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


# ---------------------------------------------------------------------------
# Helper: decode image bytes → numpy BGR
# ---------------------------------------------------------------------------

def _decode_image(data: bytes) -> np.ndarray:
    import cv2  # type: ignore
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400,
                            detail={"code": 1002, "message": "Image decode failed"})
    return img


def _success(capability: str, version: str, result: dict, elapsed_ms: float) -> dict:
    return {
        "code":             0,
        "message":          "success",
        "capability":       capability,
        "model_version":    version,
        "inference_time_ms": elapsed_ms,
        "result":           result,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    }


def _error_response(code: int, message: str, capability: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"code": code, "message": message, "capability": capability},
    )


# ---------------------------------------------------------------------------
# Health & capabilities
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", tags=["system"])
def health():
    lic = _license_status()
    caps = [
        {
            "capability":    cap,
            "version":       eng.version,
            "status":        "loaded",
        }
        for cap, eng in _engines.items()
    ]
    return {
        "status":       "healthy" if _engines else "degraded",
        "capabilities": caps,
        "license":      lic,
        "server_time":  datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/capabilities", tags=["system"])
def list_capabilities():
    return {
        "capabilities": [
            {
                "capability": cap,
                "version":    eng.version,
                "manifest":   eng.manifest,
            }
            for cap, eng in _engines.items()
        ]
    }


# ---------------------------------------------------------------------------
# License
# ---------------------------------------------------------------------------

@app.get("/api/v1/license/status", tags=["license"])
def license_status():
    return _license_status()


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

@app.post("/api/v1/infer/{capability}", tags=["inference"])
async def infer(
    capability: str,
    image: UploadFile = File(...),
    options: Optional[str] = Form(default=None),
):
    """Run inference for a specific AI capability."""
    # License check
    _check_license(capability)

    if capability not in _engines:
        raise HTTPException(
            status_code=404,
            detail={"code": 2001, "message": "Capability not found", "capability": capability},
        )

    raw  = await image.read()
    img  = _decode_image(raw)
    opts = {}
    if options:
        try:
            opts = json.loads(options)
        except Exception:
            pass

    engine = _engines[capability]
    t0     = time.perf_counter()
    try:
        result = engine.infer(img, opts)
    except Exception as exc:
        logger.error("Inference failed for %s: %s", capability, exc, exc_info=True)
        return _error_response(2004, f"Inference failed: {exc}", capability)

    elapsed = (time.perf_counter() - t0) * 1000.0
    return _success(capability, engine.version, result, round(elapsed, 2))


# ---------------------------------------------------------------------------
# Admin: hot-reload
# ---------------------------------------------------------------------------

def _verify_admin(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/api/v1/admin/reload", tags=["admin"])
async def reload_all(request: Request):
    _verify_admin(request)
    reloaded = []
    failed   = []
    for cap in list(_engines.keys()):
        mdir = resolve_model_dir(cap)
        if not mdir:
            failed.append(cap)
            continue
        try:
            _engines[cap] = ProdInferenceEngine(cap, mdir)
            reloaded.append(cap)
        except Exception as exc:
            failed.append(cap)
            logger.error("Reload %s failed: %s", cap, exc)
    return {"reloaded": reloaded, "failed": failed}


@app.post("/api/v1/admin/reload/{capability}", tags=["admin"])
async def reload_capability(capability: str, request: Request):
    _verify_admin(request)
    mdir = resolve_model_dir(capability)
    if not mdir:
        raise HTTPException(status_code=404,
                            detail=f"Model directory not found for {capability}")
    try:
        _engines[capability] = ProdInferenceEngine(capability, mdir)
        return {"reloaded": capability, "version": _engines[capability].version}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
