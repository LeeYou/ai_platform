"""Test Management API — single sample test, batch test, version compare.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import asyncio
import hmac
import io
import json
import logging
import os
import tempfile
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Logging setup — MUST run before any third-party imports so that
# import errors are captured in the log file.
# ---------------------------------------------------------------------------

MODELS_ROOT   = os.getenv("MODELS_ROOT",   "/workspace/models")
DATASETS_ROOT = os.getenv("DATASETS_ROOT", "/workspace/datasets")
LOG_DIR       = os.getenv("LOG_DIR", "/workspace/logs")
TEST_LOG_DIR  = "./data/test_logs"
TEST_STATE_FILE = "./data/test_jobs.json"
TEST_BATCH_MAX_CONCURRENCY = max(1, int(os.getenv("TEST_BATCH_MAX_CONCURRENCY", "3")))
TEST_BATCH_TIMEOUT_SECONDS = max(1, int(os.getenv("TEST_BATCH_TIMEOUT_SECONDS", "1800")))
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
        os.path.join(LOG_DIR, "test.log"),
        maxBytes=50 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    app_logger = logging.getLogger("test")
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
    from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except Exception:
    logger.critical("Failed to import application modules:\n%s", traceback.format_exc())
    sys.exit(1)

# In-memory batch job store
_batch_jobs: dict[str, dict] = {}
_batch_semaphore = asyncio.Semaphore(TEST_BATCH_MAX_CONCURRENCY)


def _persist_batch_jobs() -> None:
    os.makedirs(os.path.dirname(TEST_STATE_FILE) or ".", exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="test_jobs_", suffix=".json", dir=os.path.dirname(TEST_STATE_FILE) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(list(_batch_jobs.values()), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, TEST_STATE_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _load_batch_jobs() -> None:
    if not os.path.exists(TEST_STATE_FILE):
        return
    try:
        with open(TEST_STATE_FILE, encoding="utf-8") as f:
            jobs = json.load(f)
        _batch_jobs.clear()
        for job in jobs:
            if isinstance(job, dict) and job.get("job_id"):
                _batch_jobs[job["job_id"]] = job
    except Exception as exc:
        logger.warning("Failed to load persisted batch jobs from %s: %s", TEST_STATE_FILE, exc)


def _mark_interrupted_batch_jobs_failed() -> None:
    changed = False
    finished_at = datetime.now(timezone.utc).isoformat()
    for job in _batch_jobs.values():
        if job.get("status") in {"pending", "running"}:
            job["status"] = "failed"
            job["error_msg"] = "Service restarted before batch job completed"
            job["finished_at"] = finished_at
            changed = True
    if changed:
        _persist_batch_jobs()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(TEST_LOG_DIR, exist_ok=True)
    _load_batch_jobs()
    _mark_interrupted_batch_jobs_failed()
    logger.info("Test Management service started")
    yield
    _persist_batch_jobs()
    logger.info("Test Management service stopped")


app = FastAPI(
    title="Test Management API",
    version="1.0.0",
    description="Backend for AI model single/batch inference testing",
    lifespan=lifespan,
)

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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        if _requires_admin_auth(request):
            token = _extract_admin_token(request)
            if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
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
# Helpers
# ---------------------------------------------------------------------------

def _list_models() -> list[dict]:
    """Scan MODELS_ROOT for capability/version dirs with manifest.json."""
    results = []
    if not os.path.isdir(MODELS_ROOT):
        return results
    for cap in sorted(os.listdir(MODELS_ROOT)):
        cap_dir = os.path.join(MODELS_ROOT, cap)
        if not os.path.isdir(cap_dir):
            continue
        for version in sorted(os.listdir(cap_dir)):
            v_dir = os.path.join(cap_dir, version)
            manifest_path = os.path.join(v_dir, "manifest.json")
            if not os.path.exists(manifest_path):
                continue
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {}
            results.append({
                "capability":    cap,
                "version":       version,
                "model_dir":     v_dir,
                "manifest":      manifest,
                "last_modified": datetime.fromtimestamp(
                    os.path.getmtime(manifest_path), tz=timezone.utc
                ).isoformat(),
            })
    return results


def _sample_models(models: list[dict], limit: int = 10) -> list[dict]:
    samples = []
    for item in models[:limit]:
        samples.append({
            "capability": item.get("capability", ""),
            "version": item.get("version", ""),
            "manifest_path": os.path.join(item.get("model_dir", ""), "manifest.json"),
        })
    return samples


def _decode_image(data: bytes) -> np.ndarray:
    import cv2  # type: ignore
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image")
    return img


def _image_to_base64(img: np.ndarray) -> str:
    import base64
    import cv2  # type: ignore
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _draw_result(img: np.ndarray, result: dict, capability: str) -> np.ndarray:
    """Overlay inference result on image for visualisation."""
    import cv2  # type: ignore
    vis = img.copy()
    h, w = vis.shape[:2]

    if capability in ("desktop_recapture_detect",):
        label = result.get("label", "")
        score = result.get("score_recaptured", 0)
        color = (0, 0, 255) if result.get("is_recaptured") else (0, 200, 0)
        text  = f"{label}: {score:.2f}"
        cv2.putText(vis, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    elif capability == "face_detect":
        for det in result.get("detections", []):
            x1, y1, x2, y2 = det["bbox"]
            x1i, y1i = int(x1 * w), int(y1 * h)
            x2i, y2i = int(x2 * w), int(y2 * h)
            cv2.rectangle(vis, (x1i, y1i), (x2i, y2i), (0, 255, 0), 2)
            cv2.putText(vis, f"face {det['confidence']:.2f}",
                        (x1i, y1i - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
    else:
        label = str(result.get("top_class", ""))
        score = str(result.get("top_score", ""))
        cv2.putText(vis, f"class {label}: {score}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 128, 0), 2)

    return vis


def _resolve_dataset_path(dataset_path: str) -> str:
    root = os.path.realpath(DATASETS_ROOT)
    candidate = dataset_path
    if not os.path.isabs(candidate):
        candidate = os.path.join(DATASETS_ROOT, candidate)
    resolved = os.path.realpath(candidate)
    if resolved == root:
        raise HTTPException(status_code=400, detail="Dataset path must point to a subdirectory under DATASETS_ROOT")
    if not resolved.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Dataset path must stay within DATASETS_ROOT")
    return resolved


async def _run_batch(job_id: str, capability: str, model_dir: str, dataset_path: str) -> None:
    from inferencers import get_inferencer
    import cv2  # type: ignore

    job = _batch_jobs[job_id]
    job["status"] = "pending"
    job["error_msg"] = None
    log_path = os.path.join(TEST_LOG_DIR, f"batch_{job_id}.json")
    job["log_path"] = log_path
    _persist_batch_jobs()

    def _execute_batch() -> None:
        inferencer = get_inferencer(capability, model_dir)
        img_exts = {".jpg", ".jpeg", ".png", ".bmp"}
        samples = []
        for root, _, files in os.walk(dataset_path):
            for fn in files:
                if os.path.splitext(fn)[1].lower() in img_exts:
                    samples.append(os.path.join(root, fn))
        samples.sort()

        job["total"] = len(samples)
        job["done"] = 0
        _persist_batch_jobs()
        results = []
        deadline = time.monotonic() + TEST_BATCH_TIMEOUT_SECONDS

        for fp in samples:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Batch inference timed out after {TEST_BATCH_TIMEOUT_SECONDS} seconds")
            img = cv2.imread(fp)
            if img is None:
                continue
            try:
                r = inferencer.infer(img)
            except Exception as exc:
                r = {"error": str(exc)}
            results.append({"file": fp, **r})
            job["done"] += 1
            _persist_batch_jobs()

        correct = 0
        total_valid = 0
        for r in results:
            if "error" in r:
                continue
            total_valid += 1
            label_dir = os.path.basename(os.path.dirname(r["file"])).lower()
            if capability == "desktop_recapture_detect":
                gt = "recaptured" in label_dir
                pred = r.get("is_recaptured", False)
                if gt == pred:
                    correct += 1

        accuracy = round(correct / total_valid, 4) if total_valid > 0 else None
        report = {
            "capability": capability,
            "model_dir": model_dir,
            "total_samples": len(samples),
            "processed": total_valid,
            "accuracy": accuracy,
            "results": results,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        job["status"] = "done"
        job["accuracy"] = accuracy
        job["processed"] = total_valid
        job["finished_at"] = report["finished_at"]
        _persist_batch_jobs()

    try:
        async with _batch_semaphore:
            job["status"] = "running"
            _persist_batch_jobs()
            await asyncio.to_thread(_execute_batch)
    except Exception as exc:
        job["status"] = "failed"
        job["error_msg"] = str(exc)
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _persist_batch_jobs()
        logger.error("Batch inference job %s failed: %s", job_id, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/api/v1/models", tags=["models"])
def list_models():
    return _list_models()


@app.get("/api/v1/diagnostics", tags=["system"])
def diagnostics():
    models = _list_models()
    return {
        "auth": {
            "admin_token_configured": bool(ADMIN_TOKEN),
            "using_default_admin_token": ADMIN_TOKEN == "changeme",
            "accepted_headers": [
                "Authorization: Bearer <token>",
                "X-Admin-Token: <token>",
            ],
            "expected_frontend_token_sources": [
                "localStorage.ai_admin_token",
                "sessionStorage.ai_admin_token",
                "VITE_AI_ADMIN_TOKEN",
            ],
        },
        "models": {
            "models_root": MODELS_ROOT,
            "models_root_exists": os.path.isdir(MODELS_ROOT),
            "model_count": len(models),
            "sample_models": _sample_models(models),
        },
    }


@app.post("/api/v1/infer/single", tags=["inference"])
async def single_infer(
    capability: str = Form(...),
    version: str = Form(...),
    file: UploadFile = File(...),
):
    """Single sample inference with result visualisation."""
    from inferencers import get_inferencer

    model_dir = os.path.join(MODELS_ROOT, capability, version)
    if not os.path.isdir(model_dir):
        raise HTTPException(status_code=404, detail=f"Model not found: {capability}/{version}")

    raw = await file.read()
    try:
        img = _decode_image(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    inferencer = get_inferencer(capability, model_dir)
    result = inferencer.infer(img)

    vis = _draw_result(img, result, capability)
    vis_b64 = _image_to_base64(vis)

    return {
        "capability": capability,
        "version":    version,
        "result":     result,
        "vis_image":  vis_b64,  # base64 JPEG
    }


class BatchRequest(BaseModel):
    capability: str
    version: str
    dataset_path: str


@app.post("/api/v1/infer/batch", tags=["inference"], status_code=202)
async def batch_infer(req: BatchRequest):
    model_dir = os.path.join(MODELS_ROOT, req.capability, req.version)
    if not os.path.isdir(model_dir):
        raise HTTPException(status_code=404, detail=f"Model not found: {req.capability}/{req.version}")
    dataset_path = _resolve_dataset_path(req.dataset_path)
    if not os.path.isdir(dataset_path):
        raise HTTPException(status_code=404, detail=f"Dataset path not found: {req.dataset_path}")

    job_id = str(uuid.uuid4())
    _batch_jobs[job_id] = {
        "job_id":       job_id,
        "capability":   req.capability,
        "version":      req.version,
        "dataset_path": dataset_path,
        "status":       "pending",
        "total":        0,
        "done":         0,
        "accuracy":     None,
        "processed":    0,
        "log_path":     None,
        "created_at":   datetime.now(timezone.utc).isoformat(),
        "finished_at":  None,
        "error_msg":    None,
    }
    _persist_batch_jobs()
    asyncio.create_task(_run_batch(job_id, req.capability, model_dir, dataset_path))
    return _batch_jobs[job_id]


@app.get("/api/v1/infer/batch/{job_id}", tags=["inference"])
def get_batch_job(job_id: str):
    if job_id not in _batch_jobs:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return _batch_jobs[job_id]


@app.get("/api/v1/infer/batch/{job_id}/report", tags=["inference"])
def get_batch_report(job_id: str):
    if job_id not in _batch_jobs:
        raise HTTPException(status_code=404, detail="Batch job not found")
    log_path = _batch_jobs[job_id].get("log_path")
    if not log_path or not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Report not ready")
    with open(log_path, encoding="utf-8") as f:
        return json.load(f)


class CompareRequest(BaseModel):
    capability: str
    version_a: str
    version_b: str
    dataset_path: str
    max_samples: int = 20


@app.post("/api/v1/infer/compare", tags=["inference"])
async def compare_versions(req: CompareRequest):
    """Synchronous side-by-side comparison of two model versions."""
    import cv2  # type: ignore
    from inferencers import get_inferencer

    dir_a = os.path.join(MODELS_ROOT, req.capability, req.version_a)
    dir_b = os.path.join(MODELS_ROOT, req.capability, req.version_b)
    for d in (dir_a, dir_b):
        if not os.path.isdir(d):
            raise HTTPException(status_code=404, detail=f"Model dir not found: {d}")
    dataset_path = _resolve_dataset_path(req.dataset_path)
    if not os.path.isdir(dataset_path):
        raise HTTPException(status_code=404, detail="Dataset path not found")

    inf_a = get_inferencer(req.capability, dir_a)
    inf_b = get_inferencer(req.capability, dir_b)

    img_exts = {".jpg", ".jpeg", ".png", ".bmp"}
    samples = []
    for root, _, files in os.walk(dataset_path):
        for fn in sorted(files):
            if os.path.splitext(fn)[1].lower() in img_exts:
                samples.append(os.path.join(root, fn))
    samples = samples[: req.max_samples]

    comparisons = []
    for fp in samples:
        img = cv2.imread(fp)
        if img is None:
            continue
        r_a = inf_a.infer(img)
        r_b = inf_b.infer(img)
        comparisons.append({
            "file":    fp,
            "result_a": r_a,
            "result_b": r_b,
        })

    return {
        "capability": req.capability,
        "version_a":  req.version_a,
        "version_b":  req.version_b,
        "count":      len(comparisons),
        "comparisons": comparisons,
    }


@app.websocket("/ws/batch/{job_id}")
async def ws_batch_progress(websocket: WebSocket, job_id: str):
    token = websocket.query_params.get("token", "").strip()
    if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        while True:
            job = _batch_jobs.get(job_id)
            if not job:
                await websocket.send_text('{"type":"error","msg":"job not found"}')
                break
            import json as _json
            await websocket.send_text(_json.dumps({
                "type":     "progress",
                "status":   job["status"],
                "total":    job["total"],
                "done":     job["done"],
                "accuracy": job["accuracy"],
            }))
            if job["status"] in ("done", "failed"):
                await websocket.send_text(_json.dumps({"type": "done", "status": job["status"]}))
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# Serve frontend
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
