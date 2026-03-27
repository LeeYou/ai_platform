"""Production REST API service — Layer 1 HTTP service.

Serves AI inference requests, exposes health/capabilities/license/reload APIs.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from inference_engine import ProdInferenceEngine
from resource_resolver import (
    LICENSE_PATH,
    list_available_capabilities,
    resolve_model_dir,
)

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
            print(f"[Prod] Loaded capability: {cap} v{_engines[cap].version} from {mdir}")
        except Exception as exc:
            print(f"[Prod] Failed to load {cap}: {exc}")


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
    except Exception:
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
    yield


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
            print(f"[Prod] Reload {cap} failed: {exc}")
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
