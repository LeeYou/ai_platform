"""Build Management API — trigger CMake builds, stream build logs.

Provides a web UI for selecting AI capabilities, binding customer key pairs
(via license service proxy), and compiling customer-specific SO libraries
with the trusted public-key fingerprint compiled in.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

import asyncio
import hashlib
import logging
import os
import subprocess
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}

CPP_SOURCE_DIR = os.getenv("CPP_SOURCE_DIR", "/app/cpp")
BUILD_OUTPUT_DIR = os.getenv("BUILD_OUTPUT_DIR", "/workspace/libs/linux_x86_64")
BUILD_LOG_DIR = "./data/build_logs"
LOG_DIR = os.getenv("LOG_DIR", "./data/build_logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LICENSE_SERVICE_URL = os.getenv("LICENSE_SERVICE_URL", "http://license:8003")


# ---------------------------------------------------------------------------
# Logging setup — MUST run before any third-party imports so that
# import errors are captured in the log file.
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "build_service.log"),
        maxBytes=50 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    app_logger = logging.getLogger("build")
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
    from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    import httpx
except Exception:
    logger.critical("Failed to import application modules:\n%s", traceback.format_exc())
    sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(BUILD_LOG_DIR, exist_ok=True)
    os.makedirs(BUILD_OUTPUT_DIR, exist_ok=True)
    logger.info("Build Management service started")
    yield
    logger.info("Build Management service stopped")


app = FastAPI(
    title="Build Management API",
    version="1.0.0",
    description="Trigger CMake builds and stream build logs for AI capability SO",
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
# Schemas
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    capability: str           # e.g. "recapture_detect"
    platform: str = "linux_x86_64"
    build_type: str = "Release"
    key_pair_id: Optional[int] = None  # binds customer key pair, auto-computes fingerprint
    trusted_pubkey_sha256: Optional[str] = None  # or pass fingerprint directly
    extra_cmake_args: Optional[list[str]] = None


class BuildJob(BaseModel):
    job_id: str
    capability: str
    platform: str
    status: str               # pending | running | done | failed
    log_path: Optional[str]
    created_at: str
    finished_at: Optional[str]
    key_pair_name: Optional[str] = None
    trusted_pubkey_sha256: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _run_build(job_id: str, req: BuildRequest) -> None:
    job = _jobs[job_id]
    log_path = os.path.join(BUILD_LOG_DIR, f"{job_id}.log")
    job["log_path"] = log_path
    job["status"] = "running"
    logger.info("Build %s started: capability=%s platform=%s", job_id, req.capability, req.platform)

    build_dir = f"/tmp/build_{job_id}"
    os.makedirs(build_dir, exist_ok=True)

    # Build specific capability only
    cap_flag = f"-DBUILD_ALL_CAPS=OFF -DBUILD_CAP_{req.capability.upper()}=ON"

    # Inject trusted public key fingerprint if provided
    fingerprint = req.trusted_pubkey_sha256 or job.get("trusted_pubkey_sha256", "")
    fingerprint_flag = f'-DTRUSTED_PUBKEY_SHA256="{fingerprint}"' if fingerprint else ""

    cmake_cmd = (
        f"cmake {CPP_SOURCE_DIR} -B {build_dir} "
        f"-DCMAKE_BUILD_TYPE={req.build_type} "
        f"{cap_flag} "
        f"{fingerprint_flag} "
        + " ".join(req.extra_cmake_args or [])
    )
    build_cmd = f"cmake --build {build_dir} --parallel $(nproc)"
    install_cmd = (
        f"cmake --install {build_dir} "
        f"--prefix {BUILD_OUTPUT_DIR}/{req.capability}"
    )

    with open(log_path, "w", encoding="utf-8") as lf:
        for cmd in [cmake_cmd, build_cmd, install_cmd]:
            lf.write(f"\n$ {cmd}\n")
            lf.flush()
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for line in proc.stdout:
                text = line.decode("utf-8", errors="replace")
                lf.write(text)
                lf.flush()
            await proc.wait()
            if proc.returncode != 0:
                job["status"] = "failed"
                job["finished_at"] = datetime.now(timezone.utc).isoformat()
                logger.error("Build %s failed at command: %s (exit code %s)", job_id, cmd, proc.returncode)
                return

    job["status"] = "done"
    job["finished_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("Build %s completed successfully", job_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/api/v1/builds", response_model=list[BuildJob], tags=["builds"])
def list_builds():
    return [BuildJob(**j) for j in _jobs.values()]


@app.post("/api/v1/builds", response_model=BuildJob, status_code=201, tags=["builds"])
async def trigger_build(req: BuildRequest):
    # Resolve key_pair_id to public key fingerprint via license service
    key_pair_name = None
    fingerprint = req.trusted_pubkey_sha256 or ""
    if req.key_pair_id and not fingerprint:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{LICENSE_SERVICE_URL}/api/v1/keys")
                resp.raise_for_status()
                keys = resp.json()
                kp = next((k for k in keys if k["id"] == req.key_pair_id), None)
                if not kp:
                    raise HTTPException(status_code=400, detail=f"密钥对 ID={req.key_pair_id} 不存在")
                key_pair_name = kp.get("name", "")
                pem_bytes = kp["public_key_pem"].encode("utf-8")
                fingerprint = hashlib.sha256(pem_bytes).hexdigest()
                logger.info(
                    "Resolved key_pair_id=%s (%s) → fingerprint=%s",
                    req.key_pair_id, key_pair_name, fingerprint,
                )
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch key pairs from license service: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"无法连接授权服务获取密钥对信息: {exc}",
            )

    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "capability": req.capability,
        "platform": req.platform,
        "status": "pending",
        "log_path": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "key_pair_name": key_pair_name,
        "trusted_pubkey_sha256": fingerprint or None,
    }
    _jobs[job_id] = job
    # Store fingerprint on request so _run_build can use it
    req.trusted_pubkey_sha256 = fingerprint or None
    asyncio.create_task(_run_build(job_id, req))
    return BuildJob(**job)


@app.get("/api/v1/builds/{job_id}", response_model=BuildJob, tags=["builds"])
def get_build(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Build job not found")
    return BuildJob(**_jobs[job_id])


@app.get("/api/v1/builds/{job_id}/logs", response_class=PlainTextResponse, tags=["builds"])
def get_build_logs(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Build job not found")
    log_path = _jobs[job_id].get("log_path")
    if not log_path or not os.path.exists(log_path):
        return PlainTextResponse("(no logs yet)")
    with open(log_path, encoding="utf-8", errors="replace") as f:
        return PlainTextResponse(f.read())


@app.websocket("/ws/build/{job_id}")
async def ws_build_logs(websocket: WebSocket, job_id: str):
    """Stream build logs line-by-line via WebSocket."""
    await websocket.accept()
    if job_id not in _jobs:
        await websocket.send_text('{"type":"error","msg":"job not found"}')
        await websocket.close()
        return

    try:
        log_path = None
        # Wait for log file to appear
        for _ in range(60):
            log_path = _jobs[job_id].get("log_path")
            if log_path and os.path.exists(log_path):
                break
            await asyncio.sleep(0.5)

        if not log_path or not os.path.exists(log_path):
            await websocket.send_text('{"type":"done"}')
            return

        sent = 0
        with open(log_path, encoding="utf-8", errors="replace") as lf:
            while True:
                line = lf.readline()
                if line:
                    import json as _json
                    await websocket.send_text(_json.dumps({"type": "log", "line": line}))
                    sent += 1
                else:
                    status = _jobs[job_id]["status"]
                    if status in ("done", "failed"):
                        import json as _json
                        await websocket.send_text(_json.dumps({"type": "done", "status": status}))
                        break
                    await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Capabilities — scan cpp/capabilities/ directory
# ---------------------------------------------------------------------------

@app.get("/api/v1/capabilities", tags=["capabilities"])
def list_capabilities():
    """Return a sorted list of available AI capability names."""
    cap_dir = os.path.join(CPP_SOURCE_DIR, "capabilities")
    if not os.path.isdir(cap_dir):
        logger.warning("Capabilities directory not found: %s", cap_dir)
        return []
    caps = sorted(
        d for d in os.listdir(cap_dir)
        if os.path.isdir(os.path.join(cap_dir, d)) and not d.startswith(".")
    )
    logger.info("Found %d capabilities in %s", len(caps), cap_dir)
    return caps


# ---------------------------------------------------------------------------
# Key Pairs — proxy from license service
# ---------------------------------------------------------------------------

@app.get("/api/v1/key-pairs", tags=["key-pairs"])
async def list_key_pairs():
    """Proxy key pair list from the license management service.

    Each item includes: id, name, public_key_pem, is_active, created_at,
    plus a computed ``fingerprint`` (SHA-256 of the PEM bytes).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{LICENSE_SERVICE_URL}/api/v1/keys")
            resp.raise_for_status()
            keys = resp.json()
    except httpx.HTTPError as exc:
        logger.error("Failed to proxy key pairs from license service: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"无法连接授权服务: {exc}",
        )

    # Enrich each key pair with a computed fingerprint
    for kp in keys:
        pem = kp.get("public_key_pem", "")
        kp["fingerprint"] = hashlib.sha256(pem.encode("utf-8")).hexdigest() if pem else ""
    return keys


# ---------------------------------------------------------------------------
# Artifacts — list and download build outputs
# ---------------------------------------------------------------------------

@app.get("/api/v1/builds/{job_id}/artifacts", tags=["artifacts"])
def list_artifacts(job_id: str):
    """List output files produced by a build."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Build job not found")
    job = _jobs[job_id]
    cap = job["capability"]
    artifact_dir = os.path.join(BUILD_OUTPUT_DIR, cap)
    if not os.path.isdir(artifact_dir):
        return []
    result = []
    for root, _dirs, files in os.walk(artifact_dir):
        for fname in files:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, artifact_dir)
            result.append({
                "filename": rel,
                "size": os.path.getsize(full),
            })
    return result


@app.get("/api/v1/builds/{job_id}/artifacts/{filename:path}", tags=["artifacts"])
def download_artifact(job_id: str, filename: str):
    """Download a specific build artifact."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Build job not found")
    cap = _jobs[job_id]["capability"]
    filepath = os.path.join(BUILD_OUTPUT_DIR, cap, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(filepath, filename=os.path.basename(filename))


# ---------------------------------------------------------------------------
# Serve built frontend (Vue SPA) if present
# ---------------------------------------------------------------------------
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
