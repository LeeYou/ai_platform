"""Build Management API — trigger CMake builds, stream build logs.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

import asyncio
import logging
import os
import subprocess
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# In-memory job store (no DB needed for build service)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}

CPP_SOURCE_DIR = os.getenv("CPP_SOURCE_DIR", "/app/cpp")
BUILD_OUTPUT_DIR = os.getenv("BUILD_OUTPUT_DIR", "/workspace/libs/linux_x86_64")
BUILD_LOG_DIR = "./data/build_logs"
LOG_DIR = os.getenv("LOG_DIR", "./data/build_logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


# ---------------------------------------------------------------------------
# Logging setup
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

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    return logging.getLogger("build")


logger = _setup_logging()


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
    extra_cmake_args: Optional[list[str]] = None


class BuildJob(BaseModel):
    job_id: str
    capability: str
    platform: str
    status: str               # pending | running | done | failed
    log_path: Optional[str]
    created_at: str
    finished_at: Optional[str]


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
    cmake_cmd = (
        f"cmake {CPP_SOURCE_DIR} -B {build_dir} "
        f"-DCMAKE_BUILD_TYPE={req.build_type} "
        f"{cap_flag} "
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
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "capability": req.capability,
        "platform": req.platform,
        "status": "pending",
        "log_path": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    _jobs[job_id] = job
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
