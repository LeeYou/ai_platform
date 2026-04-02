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
import re
import shlex
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
TRAIN_SERVICE_URL = os.getenv("TRAIN_SERVICE_URL", "http://train:8001")

ALLOWED_BUILD_TYPES = {"Debug", "Release", "RelWithDebInfo", "MinSizeRel"}
# CMake -D args must match: -DVARNAME=VALUE (alphanumeric + underscore/dot/dash)
CMAKE_ARG_RE = re.compile(r"^-D[A-Za-z_][A-Za-z0-9_]*(=[\w./-]*)?$")


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

def _create_lib_symlinks(capability: str, job_id: str) -> None:
    """Create standard library symlinks (libfoo.so -> libfoo.so.1 -> libfoo.so.1.0.0)."""
    lib_dir = os.path.join(BUILD_OUTPUT_DIR, capability, "lib")
    if not os.path.isdir(lib_dir):
        logger.warning("Build %s: lib directory not found: %s", job_id, lib_dir)
        return

    try:
        for filename in os.listdir(lib_dir):
            full_path = os.path.join(lib_dir, filename)
            if not os.path.isfile(full_path):
                continue

            # Match versioned shared libraries: libfoo.so.1.0.0
            import re
            match = re.match(r'^(lib\w+)\.so\.(\d+)\.(\d+)\.(\d+)$', filename)
            if not match:
                continue

            base_name = match.group(1)  # libfoo
            major = match.group(2)      # 1
            minor = match.group(3)      # 0
            patch = match.group(4)      # 0

            # Create major version symlink: libfoo.so.1 -> libfoo.so.1.0.0
            major_link = os.path.join(lib_dir, f"{base_name}.so.{major}")
            if os.path.islink(major_link):
                os.unlink(major_link)
            elif os.path.exists(major_link):
                logger.warning("Build %s: %s exists but is not a symlink", job_id, major_link)
                continue
            os.symlink(filename, major_link)
            logger.info("Build %s: Created symlink %s -> %s", job_id, os.path.basename(major_link), filename)

            # Create development symlink: libfoo.so -> libfoo.so.1
            dev_link = os.path.join(lib_dir, f"{base_name}.so")
            if os.path.islink(dev_link):
                os.unlink(dev_link)
            elif os.path.exists(dev_link):
                logger.warning("Build %s: %s exists but is not a symlink", job_id, dev_link)
                continue
            os.symlink(f"{base_name}.so.{major}", dev_link)
            logger.info("Build %s: Created symlink %s -> %s.{major}", job_id, os.path.basename(dev_link), base_name)

    except Exception as e:
        logger.error("Build %s: Failed to create library symlinks: %s", job_id, e)
        # Don't fail the build if symlink creation fails


async def _run_build(job_id: str, req: BuildRequest) -> None:
    job = _jobs[job_id]
    log_path = os.path.join(BUILD_LOG_DIR, f"{job_id}.log")
    job["log_path"] = log_path
    job["status"] = "running"
    logger.info("Build %s started: capability=%s platform=%s", job_id, req.capability, req.platform)

    build_dir = f"/tmp/build_{job_id}"
    os.makedirs(build_dir, exist_ok=True)

    # Build argument lists — no shell expansion, safe from injection
    cmake_args = [
        "cmake", CPP_SOURCE_DIR, "-B", build_dir,
        f"-DCMAKE_BUILD_TYPE={req.build_type}",
        "-DBUILD_ALL_CAPS=OFF",
        f"-DBUILD_CAP_{req.capability.upper()}=ON",
    ]

    # Inject trusted public key fingerprint if provided
    fingerprint = req.trusted_pubkey_sha256 or job.get("trusted_pubkey_sha256", "")
    if fingerprint:
        cmake_args.append(f"-DTRUSTED_PUBKEY_SHA256={fingerprint}")

    # Extra CMake args (already validated in trigger_build)
    cmake_args.extend(req.extra_cmake_args or [])

    # Determine nproc safely
    try:
        nproc = str(os.cpu_count() or 1)
    except Exception:
        nproc = "1"

    build_args = ["cmake", "--build", build_dir, "--parallel", nproc]
    install_args = [
        "cmake", "--install", build_dir,
        "--prefix", os.path.join(BUILD_OUTPUT_DIR, req.capability),
    ]

    with open(log_path, "w", encoding="utf-8") as lf:
        for args in [cmake_args, build_args, install_args]:
            cmd_display = " ".join(shlex.quote(a) for a in args)
            lf.write(f"\n$ {cmd_display}\n")
            lf.flush()
            proc = await asyncio.create_subprocess_exec(
                *args,
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
                logger.error("Build %s failed at command: %s (exit code %s)", job_id, cmd_display, proc.returncode)
                return

    # Create library symlinks after successful build
    _create_lib_symlinks(req.capability, job_id)

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
    # --- Input validation ---
    # Validate build_type
    if req.build_type not in ALLOWED_BUILD_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"build_type 必须是以下之一: {', '.join(sorted(ALLOWED_BUILD_TYPES))}",
        )

    # Validate capability against actual directory listing
    cap_dir = os.path.join(CPP_SOURCE_DIR, "capabilities")
    if os.path.isdir(cap_dir):
        valid_caps = {
            d for d in os.listdir(cap_dir)
            if os.path.isdir(os.path.join(cap_dir, d)) and not d.startswith(".")
        }
        if req.capability not in valid_caps:
            raise HTTPException(status_code=400, detail=f"无效的能力名称: {req.capability}")
    elif not re.match(r"^[a-z][a-z0-9_]*$", req.capability):
        raise HTTPException(status_code=400, detail=f"无效的能力名称: {req.capability}")

    # Validate extra cmake args (must be -DKEY=VALUE format only)
    for arg in (req.extra_cmake_args or []):
        if not CMAKE_ARG_RE.match(arg):
            raise HTTPException(
                status_code=400,
                detail=f"无效的 CMake 参数: {arg}（格式需为 -DNAME=VALUE）",
            )

    # Validate fingerprint format if provided directly
    if req.trusted_pubkey_sha256 and not re.match(r"^[a-f0-9]{64}$", req.trusted_pubkey_sha256):
        raise HTTPException(
            status_code=400,
            detail="trusted_pubkey_sha256 必须是 64 位小写十六进制字符串",
        )

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
# Capabilities — fetch from Training Service API
# ---------------------------------------------------------------------------

@app.get("/api/v1/capabilities", tags=["capabilities"])
async def list_capabilities():
    """Return capabilities from Training Service that have completed models.

    This fetches capability data from the Training Service API (which manages
    capability metadata in a database). Only capabilities that are registered
    in the training system and have source code can be compiled.

    For production deployment, the Production Service scans directories directly
    since it runs standalone without access to internal APIs.
    """
    try:
        # Fetch capabilities from Training Service API
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{TRAIN_SERVICE_URL}/api/v1/capabilities")
            resp.raise_for_status()
            train_caps = resp.json()
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch capabilities from training service: %s", exc)
        # Fallback to empty list if training service unavailable
        return []

    # Get capabilities that exist in source code
    cap_dir = os.path.join(CPP_SOURCE_DIR, "capabilities")
    source_caps = set()
    if os.path.isdir(cap_dir):
        source_caps = set(
            d for d in os.listdir(cap_dir)
            if os.path.isdir(os.path.join(cap_dir, d)) and not d.startswith(".")
        )
        logger.info("Found %d capabilities in source: %s", len(source_caps), sorted(source_caps))
    else:
        logger.warning("Capabilities directory not found: %s", cap_dir)

    # Filter to only capabilities that have BOTH:
    # 1. Registered in training service (trained model exists)
    # 2. Source code exists (can compile)
    available = []
    for cap in train_caps:
        cap_name = cap.get("name", "")
        if cap_name in source_caps:
            available.append(cap_name)

    logger.info("Returning %d buildable capabilities (from training API + source): %s",
                len(available), available)
    return sorted(available)


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
    artifact_dir = os.path.realpath(os.path.join(BUILD_OUTPUT_DIR, cap))
    filepath = os.path.realpath(os.path.join(artifact_dir, filename))
    # Prevent path traversal
    if not filepath.startswith(artifact_dir + os.sep) and filepath != artifact_dir:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(filepath, filename=os.path.basename(filename))


@app.get("/api/v1/builds/{job_id}/download-package", tags=["artifacts"])
def download_package(job_id: str):
    """Download all build artifacts as a tar.gz package."""
    import tarfile
    import tempfile

    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Build job not found")

    job = _jobs[job_id]
    cap = job["capability"]
    artifact_dir = os.path.realpath(os.path.join(BUILD_OUTPUT_DIR, cap))

    if not os.path.isdir(artifact_dir):
        raise HTTPException(status_code=404, detail="No artifacts found for this build")

    # Create temporary tar.gz file
    temp_fd, temp_path = tempfile.mkstemp(suffix=".tar.gz", prefix=f"build_{job_id}_")
    try:
        os.close(temp_fd)
        with tarfile.open(temp_path, "w:gz") as tar:
            tar.add(artifact_dir, arcname=cap)

        package_name = f"{cap}_{job_id[:8]}.tar.gz"
        return FileResponse(
            temp_path,
            filename=package_name,
            media_type="application/gzip",
            background=None  # Keep file until response completes
        )
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        logger.error("Failed to create package for build %s: %s", job_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to create package: {str(e)}")


# ---------------------------------------------------------------------------
# Serve built frontend (Vue SPA) if present
# ---------------------------------------------------------------------------
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
