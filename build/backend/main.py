"""Build Management API — trigger CMake builds, stream build logs.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

import asyncio
import os
import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# In-memory job store (no DB needed for build service)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}

CPP_SOURCE_DIR = os.getenv("CPP_SOURCE_DIR", "/app/cpp")
BUILD_OUTPUT_DIR = os.getenv("BUILD_OUTPUT_DIR", "/workspace/libs/linux_x86_64")
LOG_DIR = "./data/build_logs"


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(BUILD_OUTPUT_DIR, exist_ok=True)
    yield


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
    log_path = os.path.join(LOG_DIR, f"{job_id}.log")
    job["log_path"] = log_path
    job["status"] = "running"

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
                return

    job["status"] = "done"
    job["finished_at"] = datetime.now(timezone.utc).isoformat()


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
