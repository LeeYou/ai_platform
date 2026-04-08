"""Production REST API service — Layer 1 HTTP service.

Serves AI inference requests, exposes health/capabilities/license/reload APIs.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

# CST timezone (UTC+8) - Standard timezone for all license operations
CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# Logging setup — MUST run before any third-party / app imports so that
# import errors are captured in the log file.
# ---------------------------------------------------------------------------

LOG_DIR = os.getenv("LOG_DIR", "/mnt/ai_platform/logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()


class _HealthCheckFilter(logging.Filter):
    """Suppress high-frequency health-probe entries from uvicorn access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /api/v1/health" not in record.getMessage()


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

    # Silence health-probe noise from uvicorn's built-in access logger.
    logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())

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

    from ai_runtime_ctypes import (
        AI_OK,
        AI_ERR_CAPABILITY_MISSING,
        AI_ERR_LICENSE_EXPIRED,
        AI_ERR_LICENSE_INVALID,
        destroy_runtime,
        get_runtime,
        init_runtime,
    )
    from resource_resolver import (
        LICENSE_PATH,
        PUBKEY_PATH,
        TRUSTED_PUBKEY_SHA256,
        list_available_capabilities,
        resolve_libs_dir,
        resolve_model_dir,
        resolve_models_dir,
        resolve_runtime_so_path,
    )
    from pipeline_engine import (
        delete_pipeline_file,
        execute_pipeline,
        get_pipeline,
        list_pipelines,
        save_pipeline,
        validate_pipeline,
    )
except Exception:
    logger.critical("Failed to import application modules:\n%s", traceback.format_exc())
    sys.exit(1)

try:
    from ab_testing import ABTestManager
except Exception:
    logger.error("Failed to import A/B testing module, falling back to disabled manager:\n%s", traceback.format_exc())

    class ABTestManager:  # type: ignore[no-redef]
        def __init__(self, _config_dir: str) -> None:
            self._tests: dict[str, dict] = {}

        def reload(self) -> None:
            self._tests.clear()

        def get_version_for_request(self, _capability: str, _session_id: str | None = None) -> str:
            return "current"

        def get_test_info(self, _capability: str) -> dict[str, Any]:
            return {}

        def list_active_tests(self) -> dict[str, dict]:
            return {}

# ---------------------------------------------------------------------------
# Admin token (simple bearer auth for reload endpoint)
# ---------------------------------------------------------------------------

ADMIN_TOKEN = os.getenv("AI_ADMIN_TOKEN", "changeme")
MAX_UPLOAD_BYTES = max(1, int(os.getenv("AI_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))))
INFER_MAX_CONCURRENCY = max(1, int(os.getenv("AI_INFER_MAX_CONCURRENCY", "16")))
INFER_CONCURRENCY_TIMEOUT_SECONDS = max(
    1,
    int(os.getenv("AI_INFER_CONCURRENCY_TIMEOUT_SECONDS", "30")),
)
AB_TEST_CONFIG_DIR = os.getenv(
    "AI_AB_TEST_CONFIG_DIR",
    os.path.join(os.getenv("MOUNT_ROOT", "/mnt/ai_platform"), "ab_tests"),
)
_infer_request_semaphore = asyncio.Semaphore(INFER_MAX_CONCURRENCY)
ab_manager = ABTestManager(AB_TEST_CONFIG_DIR)
_runtime_libs_stage_dir: str | None = None
_runtime_dependency_handles: list[ctypes.CDLL] = []

# ---------------------------------------------------------------------------
# Runtime initialization
# ---------------------------------------------------------------------------

def _cleanup_runtime_libs_stage_dir() -> None:
    global _runtime_libs_stage_dir, _runtime_dependency_handles
    if _runtime_libs_stage_dir and os.path.isdir(_runtime_libs_stage_dir):
        shutil.rmtree(_runtime_libs_stage_dir, ignore_errors=True)
    _runtime_libs_stage_dir = None
    _runtime_dependency_handles = []


def _is_shared_library_filename(name: str) -> bool:
    return bool(re.search(r"\.so(?:\.\d+)*$", name))


def _is_runtime_plugin_filename(name: str, capability: str) -> bool:
    prefix = f"lib{capability}.so"
    if name == prefix:
        return True
    if not name.startswith(prefix + "."):
        return False
    suffix = name[len(prefix) + 1:]
    return bool(suffix) and all(part.isdigit() for part in suffix.split("."))


def _select_runtime_plugin_path(capability: str, candidates: list[str]) -> str:
    preferred_name = f"lib{capability}.so"
    return sorted(
        candidates,
        key=lambda path: (
            os.path.basename(path) != preferred_name,
            len(os.path.basename(path)),
            os.path.basename(path),
        ),
    )[0]


def _discover_nested_runtime_libs(libs_dir: str) -> tuple[list[str], list[str]]:
    plugin_paths: list[str] = []
    dependency_paths: set[str] = set()

    for root, _, files in os.walk(libs_dir, followlinks=True):
        if os.path.basename(root) != "lib":
            continue
        capability_root = os.path.dirname(root)
        capability = os.path.basename(capability_root)
        if capability == "current":
            capability = os.path.basename(os.path.dirname(capability_root))
        shared_objects = [
            os.path.join(root, name)
            for name in files
            if _is_shared_library_filename(name)
        ]
        if not shared_objects:
            continue

        plugin_candidates = [
            path for path in shared_objects
            if _is_runtime_plugin_filename(os.path.basename(path), capability)
        ]
        if not plugin_candidates:
            continue

        selected_plugin = _select_runtime_plugin_path(capability, plugin_candidates)
        plugin_paths.append(selected_plugin)

        for path in shared_objects:
            basename = os.path.basename(path)
            if path == selected_plugin or basename.startswith("libai_runtime.so"):
                continue
            if path not in plugin_candidates:
                dependency_paths.add(path)

    return sorted(set(plugin_paths)), sorted(dependency_paths)


def _preload_runtime_dependencies(dependency_paths: list[str]) -> None:
    global _runtime_dependency_handles
    if not dependency_paths:
        return

    mode = getattr(ctypes, "RTLD_GLOBAL", 0)
    handles: list[ctypes.CDLL] = []
    for dependency_path in dependency_paths:
        try:
            handles.append(ctypes.CDLL(dependency_path, mode=mode))
        except OSError as exc:
            logger.warning("Failed to preload runtime dependency %s: %s", dependency_path, exc)
    _runtime_dependency_handles = handles


def _prepare_runtime_libs_dir(libs_dir: str) -> str:
    """Stage nested shared libraries into a flat directory for the native loader."""
    global _runtime_libs_stage_dir
    if not os.path.isdir(libs_dir):
        return libs_dir

    direct_shared_objects = [
        name for name in os.listdir(libs_dir)
        if os.path.isfile(os.path.join(libs_dir, name)) and _is_shared_library_filename(name)
    ]
    if direct_shared_objects:
        return libs_dir

    plugin_paths, dependency_paths = _discover_nested_runtime_libs(libs_dir)
    if not plugin_paths:
        return libs_dir

    _cleanup_runtime_libs_stage_dir()
    stage_dir = tempfile.mkdtemp(prefix="ai_runtime_libs_")
    for source_path in plugin_paths:
        target_path = os.path.join(stage_dir, os.path.basename(source_path))
        if os.path.lexists(target_path):
            continue
        try:
            os.symlink(source_path, target_path)
        except OSError:
            shutil.copy2(source_path, target_path)

    _preload_runtime_dependencies(dependency_paths)
    _runtime_libs_stage_dir = stage_dir
    logger.info(
        "Prepared staged runtime plugin directory %s from %s with %d plugin(s) and %d preloaded dependency library(ies)",
        stage_dir, libs_dir, len(plugin_paths), len(dependency_paths),
    )
    return stage_dir


def _derive_pubkey_path_from_license(license_path: str) -> str:
    if not license_path:
        return ""
    license_dir = os.path.dirname(license_path)
    if not license_dir:
        return ""
    return os.path.join(license_dir, "pubkey.pem")


def _resolve_effective_pubkey_path() -> str:
    env_pubkey_path = os.getenv("AI_PUBKEY_PATH", "").strip()
    if env_pubkey_path:
        return env_pubkey_path

    configured_pubkey_path = (PUBKEY_PATH or "").strip()
    if configured_pubkey_path and os.path.exists(configured_pubkey_path):
        return configured_pubkey_path

    derived_pubkey_path = _derive_pubkey_path_from_license(LICENSE_PATH)
    if derived_pubkey_path:
        return derived_pubkey_path

    return configured_pubkey_path


def _init_runtime() -> bool:
    """Initialize C++ Runtime layer with SO directory, models, and license."""
    runtime_so = resolve_runtime_so_path()
    if not runtime_so:
        logger.error("libai_runtime.so not found in mount or built-in paths")
        logger.error("Production service REQUIRES C++ Runtime SO — cannot start")
        return False

    libs_dir = resolve_libs_dir()
    loader_libs_dir = _prepare_runtime_libs_dir(libs_dir)
    models_dir = resolve_models_dir()
    effective_pubkey_path = _resolve_effective_pubkey_path()

    logger.info("Initializing C++ Runtime:")
    logger.info("  Runtime SO:    %s", runtime_so)
    logger.info("  Libs dir:      %s", libs_dir)
    if loader_libs_dir != libs_dir:
        logger.info("  Loader dir:    %s", loader_libs_dir)
    logger.info("  Models dir:    %s", models_dir)
    logger.info("  License path:  %s", LICENSE_PATH)
    if effective_pubkey_path:
        logger.info("  Pubkey path:   %s", effective_pubkey_path)

    if effective_pubkey_path:
        os.environ["AI_PUBKEY_PATH"] = effective_pubkey_path

    success = init_runtime(runtime_so, loader_libs_dir, models_dir, LICENSE_PATH)
    if not success:
        logger.error("Failed to initialize C++ Runtime — check logs above")
        return False

    runtime = get_runtime()
    if runtime:
        caps = runtime.get_capabilities()
        logger.info("Runtime loaded %d capabilities: %s", len(caps), [c["name"] for c in caps])
        _log_runtime_capability_hints(runtime)

    ab_manager.reload()
    logger.info("A/B test manager loaded %d active tests", len(ab_manager.list_active_tests()))

    return True


# ---------------------------------------------------------------------------
# License status helper
# ---------------------------------------------------------------------------

def _runtime_license_status(runtime: Any | None = None) -> dict[str, Any]:
    runtime = runtime or get_runtime()
    if not runtime:
        return {
            "status": "unavailable",
            "license_id": None,
            "valid_from": None,
            "valid_until": None,
            "days_remaining": 0,
            "capabilities": [],
        }
    status = runtime.get_license_status()
    if isinstance(status, dict):
        return status
    logger.warning("Runtime license status unavailable")
    return {
        "status": "unavailable",
        "license_id": None,
        "valid_from": None,
        "valid_until": None,
        "days_remaining": 0,
        "capabilities": [],
    }


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not _init_runtime():
        logger.critical("Failed to initialize C++ Runtime — exiting")
        sys.exit(1)
    runtime = get_runtime()
    caps = runtime.get_capabilities() if runtime else []
    logger.info("Production AI service started — %d capabilities loaded", len(caps))
    yield
    destroy_runtime()
    _cleanup_runtime_libs_stage_dir()
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
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length", "").strip()
            if content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES:
                return _payload_too_large_response()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if request.url.path != "/api/v1/health":
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


def _load_capability_preprocess(capability: str) -> dict[str, Any]:
    model_dir = resolve_model_dir(capability)
    if not model_dir:
        return {}
    preprocess_path = os.path.join(model_dir, "preprocess.json")
    try:
        with open(preprocess_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _resize_image_for_capability(capability: str, img: np.ndarray) -> tuple[np.ndarray, dict[str, int] | None]:
    resize_cfg = _load_capability_preprocess(capability).get("resize", {})
    width = int(resize_cfg.get("width") or 0)
    height = int(resize_cfg.get("height") or 0)
    if width <= 0 or height <= 0:
        return img, None
    if img.shape[1] == width and img.shape[0] == height:
        return img, {"width": width, "height": height}

    import cv2  # type: ignore

    resized = cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)
    return resized, {"width": width, "height": height}


def _load_capability_build_info(capability: str) -> dict[str, Any]:
    from resource_resolver import resolve_lib_path

    lib_path = resolve_lib_path(capability)
    if not lib_path:
        return {}

    lib_dir = os.path.dirname(lib_path)
    capability_root = os.path.dirname(lib_dir)
    candidates = [
        os.path.join(capability_root, "build_info.json"),
        os.path.join(os.path.dirname(capability_root), "build_info.json"),
    ]
    for candidate in candidates:
        try:
            with open(candidate, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data["_path"] = candidate
                return data
        except Exception:
            continue
    return {}


def _summarize_capability_runtime(capability: str) -> dict[str, Any]:
    build_info = _load_capability_build_info(capability)
    runtime_gpu_expected = build_info.get("onnxruntime_package") == "gpu"
    return {
        "build_info": build_info,
        "runtime_gpu_expected": runtime_gpu_expected if build_info else None,
    }


def _success(
    capability: str,
    version: str,
    result: dict,
    elapsed_ms: float,
    ab_test: Optional[dict[str, Any]] = None,
) -> dict:
    payload = {
        "code":             0,
        "message":          "success",
        "capability":       capability,
        "model_version":    version,
        "inference_time_ms": elapsed_ms,
        "result":           result,
        "timestamp":        datetime.now(CST).isoformat(),
    }
    if ab_test:
        payload["ab_test"] = ab_test
    return payload


def _error_response(
    code: int,
    message: str,
    capability: str = "",
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "capability": capability},
    )


def _acquire_failure_response(runtime: Any, capability: str) -> JSONResponse:
    runtime_error = runtime.get_last_error() if runtime and hasattr(runtime, "get_last_error") else None
    if isinstance(runtime_error, dict) and runtime_error.get("code"):
        return _error_response(
            int(runtime_error["code"]),
            str(runtime_error.get("message", "Inference failed")),
            capability,
            status_code=int(runtime_error.get("status_code", 403)),
        )
    return _error_response(3001, "Instance pool timeout or capability not available", capability)


def _validate_capability_name(capability: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", capability):
        raise HTTPException(status_code=400, detail={"code": 2001, "message": "Invalid capability name"})


def _payload_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={"code": 1003, "message": f"Request body too large (max {MAX_UPLOAD_BYTES} bytes)"},
    )


def _check_upload_size(raw: bytes) -> None:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": 1003, "message": f"Image payload too large (max {MAX_UPLOAD_BYTES} bytes)"},
        )


@asynccontextmanager
async def _acquire_infer_slot():
    acquired = False
    try:
        await asyncio.wait_for(
            _infer_request_semaphore.acquire(),
            timeout=INFER_CONCURRENCY_TIMEOUT_SECONDS,
        )
        acquired = True
        yield
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": 3002, "message": "Inference concurrency limit reached"},
        ) from exc
    finally:
        if acquired:
            _infer_request_semaphore.release()


def _available_pipeline_capabilities() -> list[str]:
    runtime = get_runtime()
    if runtime:
        return [cap.get("name", "") for cap in runtime.get_capabilities() if cap.get("name")]
    return [cap.get("capability", "") for cap in list_available_capabilities() if cap.get("capability")]


def _get_runtime_capability_version(runtime: Any, capability: str) -> str:
    for cap_info in runtime.get_capabilities():
        if cap_info.get("name") == capability:
            return cap_info.get("version", "unknown")
    return "unknown"


def _infer_for_pipeline(capability: str, image_bytes: bytes, _opts: dict) -> dict:
    _validate_capability_name(capability)
    runtime = get_runtime()
    if not runtime:
        raise ValueError("Runtime not initialized")

    handle = runtime.acquire(capability, timeout_ms=30000)
    if not handle:
        response = _acquire_failure_response(runtime, capability)
        body = json.loads(response.body)
        raise HTTPException(status_code=response.status_code, detail=body)

    try:
        img = _decode_image(image_bytes)
        img, _ = _resize_image_for_capability(capability, img)
        height, width, channels = img.shape
        result = runtime.infer(handle, img.tobytes(), width, height, channels)
        if result.get("error_code", 0) != AI_OK:
            raise ValueError(result.get("error_msg", "Inference failed"))
        return result.get("result", {})
    finally:
        runtime.release(handle)


def _capability_diagnostics() -> dict:
    runtime = get_runtime()
    runtime_so_path = resolve_runtime_so_path()
    libs_dir = resolve_libs_dir()
    models_dir = resolve_models_dir()
    effective_pubkey_path = _resolve_effective_pubkey_path()
    discovered_caps = list_available_capabilities()
    loaded_caps = runtime.get_capabilities() if runtime else []
    return {
        "runtime_initialized": bool(runtime),
        "runtime_so_path": runtime_so_path,
        "runtime_so_found": bool(runtime_so_path and os.path.exists(runtime_so_path)),
        "libs_dir": libs_dir,
        "libs_dir_exists": os.path.isdir(libs_dir),
        "models_dir": models_dir,
        "models_dir_exists": os.path.isdir(models_dir),
        "license_path": LICENSE_PATH,
        "license_exists": os.path.exists(LICENSE_PATH),
        "pubkey_path": effective_pubkey_path,
        "pubkey_exists": os.path.exists(effective_pubkey_path),
        "loaded_capabilities": [cap.get("name", "") for cap in loaded_caps if cap.get("name")],
        "loaded_capability_details": [
            {
                **cap,
                **_summarize_capability_runtime(cap.get("name", "")),
            }
            for cap in loaded_caps
        ],
        "discovered_model_capabilities": [
            cap.get("capability", "") for cap in discovered_caps if cap.get("capability")
        ],
        "discovered_models": [
            {
                "capability": cap.get("capability", ""),
                "version": cap.get("version", "unknown"),
                "model_dir": cap.get("model_dir", ""),
                "real_model_dir": cap.get("real_model_dir", ""),
                "source": cap.get("source", ""),
                "manifest": cap.get("manifest", {}),
                "preprocess": cap.get("preprocess", {}),
            }
            for cap in discovered_caps
        ],
    }


def _detect_gpu_available() -> bool:
    try:
        if os.path.exists("/dev/nvidia0") or os.path.exists("/proc/driver/nvidia/version"):
            return True
    except OSError as exc:
        logger.debug("GPU device probe failed: %s", exc)

    try:
        result = subprocess.run(
            ["nvidia-smi"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("nvidia-smi probe failed: %s", exc)
        return False


def _log_runtime_capability_hints(runtime: Any) -> None:
    gpu_available = _detect_gpu_available()
    for cap_info in runtime.get_capabilities():
        capability = cap_info.get("name", "")
        if not capability:
            continue
        summary = _summarize_capability_runtime(capability)
        build_info = summary["build_info"]
        if build_info:
            logger.info(
                "Capability %s build info: builder=%s toolchain=%s onnxruntime=%s metadata=%s",
                capability,
                build_info.get("builder_image", "unknown"),
                build_info.get("builder_toolchain_profile", "unknown"),
                build_info.get("onnxruntime_package", "unknown"),
                build_info.get("_path", ""),
            )
        else:
            logger.warning(
                "Capability %s build_info.json not found beside installed libraries; GPU-vs-CPU artifact source is unknown",
                capability,
            )
        if gpu_available and build_info and build_info.get("onnxruntime_package") != "gpu":
            logger.error(
                "Capability %s is running on a GPU host but installed artifact metadata says onnxruntime_package=%s; "
                "rebuild/reinstall this capability from the GPU builder to avoid slow CPU execution",
                capability,
                build_info.get("onnxruntime_package"),
            )


# ---------------------------------------------------------------------------
# Health & capabilities
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", tags=["system"])
def health():
    """Health check endpoint with capabilities and license status."""
    runtime = get_runtime()
    diagnostics = _capability_diagnostics()
    lic = _runtime_license_status(runtime)

    # Get capabilities from C++ Runtime
    caps = []
    if runtime:
        caps_data = runtime.get_capabilities()
        caps = [
            {
                "capability": cap_info.get("name", ""),
                "version":    cap_info.get("version", "unknown"),
                "status":     cap_info.get("status", "loaded"),
            }
            for cap_info in caps_data
        ]

    # GPU availability detection - check CUDA device files
    return {
        "status":        "healthy" if caps else "degraded",
        "capabilities":  caps,
        "license":       lic,
        "server_time":   datetime.now(CST).isoformat(),
        "gpu_available": _detect_gpu_available(),
        "runtime_initialized": diagnostics["runtime_initialized"],
        "loaded_capability_count": len(diagnostics["loaded_capabilities"]),
        "discovered_model_capability_count": len(diagnostics["discovered_model_capabilities"]),
    }


@app.get("/api/v1/capabilities", tags=["system"])
def list_capabilities():
    """List all loaded capabilities with their versions and manifests.

    ARCHITECTURE NOTE:
    Production service scans directories directly (not API calls) because:
    1. Production runs standalone after deployment (no access to internal services)
    2. Capabilities are discovered from: built-in directories + mounted host paths
    3. This enables hot-reload: new capabilities added to host paths are auto-discovered
    4. Runtime dynamically loads .so files and models from discovered directories

    Internal services (train/test/license/build) use API-based communication.
    """
    runtime = get_runtime()
    if not runtime:
        return {"capabilities": []}

    caps_data = runtime.get_capabilities()
    result = []

    for cap_info in caps_data:
        cap_name = cap_info.get("name", "")
        # Try to read manifest from model directory
        model_dir = resolve_model_dir(cap_name)
        manifest = {}
        if model_dir:
            manifest_path = os.path.join(model_dir, "manifest.json")
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                pass

        result.append({
            "capability": cap_name,
            "version":    cap_info.get("version", "unknown"),
            "manifest":   manifest,
        })

    return {"capabilities": result}


@app.get("/api/v1/capabilities/diagnostics", tags=["system"])
def capability_diagnostics():
    return _capability_diagnostics()


# ---------------------------------------------------------------------------
# License
# ---------------------------------------------------------------------------

@app.get("/api/v1/license/status", tags=["license"])
def license_status():
    return _runtime_license_status()


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

@app.post("/api/v1/infer/{capability}", tags=["inference"])
async def infer(
    capability: str,
    request: Request,
    image: UploadFile = File(...),
    options: Optional[str] = Form(default=None),
):
    """Run inference for a specific AI capability using C++ Runtime instance pool."""
    async with _acquire_infer_slot():
        _validate_capability_name(capability)

        runtime = get_runtime()
        if not runtime:
            raise HTTPException(
                status_code=500,
                detail={"code": 5001, "message": "Runtime not initialized"},
            )

        raw = await image.read()
        _check_upload_size(raw)
        img = _decode_image(raw)
        original_height, original_width = img.shape[:2]
        img, resized_to = _resize_image_for_capability(capability, img)

        if options:
            try:
                json.loads(options)
            except Exception:
                pass

        session_id = request.headers.get("X-Session-ID", "").strip() or None
        selected_version = ab_manager.get_version_for_request(capability, session_id)

        t0 = time.perf_counter()
        handle = runtime.acquire(capability, timeout_ms=30000)
        if not handle:
            logger.warning("Failed to acquire instance for %s (pool exhausted or capability not found)", capability)
            return _acquire_failure_response(runtime, capability)

        try:
            height, width, channels = img.shape
            img_bytes = img.tobytes()
            result = runtime.infer(handle, img_bytes, width, height, channels)

            if result.get("error_code", 0) != AI_OK:
                return _error_response(
                    result.get("error_code", 5001),
                    result.get("error_msg", "Inference failed"),
                    capability
                )

            elapsed = (time.perf_counter() - t0) * 1000.0
            version = _get_runtime_capability_version(runtime, capability)
            if resized_to:
                result.setdefault("result", {})["input_size"] = {
                    "width": original_width,
                    "height": original_height,
                }
                result["result"]["preprocessed_size"] = resized_to
            ab_info = ab_manager.get_test_info(capability)
            if ab_info:
                ab_info = {
                    "strategy": ab_info.get("strategy", "random"),
                    "selected_version": selected_version,
                    "applied_version": version,
                    "selection_matches_runtime": selected_version in ("current", version),
                }

            return _success(
                capability,
                version,
                result.get("result", {}),
                round(elapsed, 2),
                ab_test=ab_info or None,
            )

        except Exception as exc:
            logger.error("Inference failed for %s: %s", capability, exc, exc_info=True)
            return _error_response(2004, "Inference failed", capability)
        finally:
            runtime.release(handle)


# ---------------------------------------------------------------------------
# Admin: hot-reload
# ---------------------------------------------------------------------------

def _verify_admin(request: Request) -> None:
    import hmac
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/api/v1/admin/reload", tags=["admin"])
async def reload_all(request: Request):
    """Trigger hot reload for all capabilities via C++ Runtime."""
    _verify_admin(request)
    runtime = get_runtime()
    if not runtime:
        raise HTTPException(status_code=500, detail="Runtime not initialized")

    caps = runtime.get_capabilities()
    reloaded = []
    failed   = []

    for cap_info in caps:
        cap_name = cap_info.get("name", "")
        ret = runtime.reload(cap_name)
        if ret == AI_OK:
            reloaded.append(cap_name)
        else:
            failed.append(cap_name)
            logger.error("Reload %s failed with error code %d", cap_name, ret)

    return {"reloaded": reloaded, "failed": failed}


@app.post("/api/v1/admin/reload/{capability}", tags=["admin"])
async def reload_capability(capability: str, request: Request):
    """Trigger hot reload for a specific capability via C++ Runtime."""
    _verify_admin(request)
    _validate_capability_name(capability)
    runtime = get_runtime()
    if not runtime:
        raise HTTPException(status_code=500, detail="Runtime not initialized")

    ret = runtime.reload(capability)
    if ret != AI_OK:
        if ret == AI_ERR_CAPABILITY_MISSING:
            raise HTTPException(status_code=404, detail=f"Capability not found: {capability}")
        raise HTTPException(status_code=500, detail=f"Reload failed with error code {ret}")

    # Get updated version info
    caps = runtime.get_capabilities()
    version = "unknown"
    for cap_info in caps:
        if cap_info.get("name") == capability:
            version = cap_info.get("version", "unknown")
            break

    return {"reloaded": capability, "version": version}


@app.get("/api/v1/admin/ab_tests", tags=["admin"])
def list_ab_tests(request: Request):
    """List active A/B tests."""
    _verify_admin(request)
    return {"ab_tests": ab_manager.list_active_tests()}


@app.post("/api/v1/admin/ab_tests/reload", tags=["admin"])
async def reload_ab_tests(request: Request):
    """Reload A/B test configurations from disk."""
    _verify_admin(request)
    ab_manager.reload()
    return {
        "status": "reloaded",
        "active_tests": len(ab_manager.list_active_tests()),
        "ab_tests": ab_manager.list_active_tests(),
    }


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

@app.get("/api/v1/pipelines", tags=["pipelines"])
def list_all_pipelines():
    """List all pipeline definitions."""
    return {"pipelines": list_pipelines()}


@app.post("/api/v1/pipelines", tags=["pipelines"])
async def create_pipeline_endpoint(request: Request):
    """Create a new pipeline definition."""
    _verify_admin(request)
    body = await request.json()
    if not body.get("pipeline_id"):
        raise HTTPException(status_code=400, detail="missing 'pipeline_id'")
    existing = get_pipeline(body["pipeline_id"])
    if existing:
        raise HTTPException(status_code=409,
                            detail=f"Pipeline '{body['pipeline_id']}' already exists")
    save_pipeline(body)
    return {"status": "created", "pipeline_id": body["pipeline_id"]}


@app.get("/api/v1/pipelines/{pipeline_id}", tags=["pipelines"])
def get_pipeline_endpoint(pipeline_id: str):
    """Get a single pipeline definition."""
    p = get_pipeline(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")
    return p


@app.put("/api/v1/pipelines/{pipeline_id}", tags=["pipelines"])
async def update_pipeline_endpoint(pipeline_id: str, request: Request):
    """Update a pipeline definition."""
    _verify_admin(request)
    body = await request.json()
    body["pipeline_id"] = pipeline_id
    save_pipeline(body)
    return {"status": "updated", "pipeline_id": pipeline_id}


@app.delete("/api/v1/pipelines/{pipeline_id}", tags=["pipelines"])
async def delete_pipeline_endpoint(pipeline_id: str, request: Request):
    _verify_admin(request)
    if not delete_pipeline_file(pipeline_id):
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")
    return {"status": "deleted", "pipeline_id": pipeline_id}


@app.post("/api/v1/pipelines/{pipeline_id}/validate", tags=["pipelines"])
def validate_pipeline_endpoint(pipeline_id: str):
    """Validate a pipeline definition."""
    p = get_pipeline(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")
    available = _available_pipeline_capabilities()
    errors = validate_pipeline(p, available)
    return {"pipeline_id": pipeline_id, "valid": len(errors) == 0, "errors": errors}


@app.post("/api/v1/pipeline/{pipeline_id}/run", tags=["pipelines"])
async def run_pipeline_endpoint(
    pipeline_id: str,
    image: UploadFile = File(...),
    options: Optional[str] = Form(default=None),
):
    """Execute a pipeline."""
    async with _acquire_infer_slot():
        p = get_pipeline(pipeline_id)
        if not p:
            raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")
        if not p.get("enabled", True):
            raise HTTPException(status_code=400,
                                detail=f"Pipeline '{pipeline_id}' is disabled")

        raw = await image.read()
        _check_upload_size(raw)
        global_opts: dict = {}
        if options:
            try:
                global_opts = json.loads(options)
            except Exception:
                pass

        result = execute_pipeline(p, raw, _infer_for_pipeline, global_opts)
        return result


# ---------------------------------------------------------------------------
# Frontend static files (must be last — catch-all for SPA routing)
# ---------------------------------------------------------------------------

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

if os.path.isdir(_FRONTEND_DIR):
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    @app.get("/", include_in_schema=False)
    async def frontend_root():
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))

    # Serve static assets (JS/CSS/images)
    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIR, "assets")),
              name="frontend-assets")

    # SPA fallback — any non-API path serves index.html
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Only serve frontend for non-API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        # Prevent path traversal: resolve and verify within frontend dir
        from pathlib import Path
        frontend_root_path = Path(_FRONTEND_DIR).resolve()
        requested = (frontend_root_path / full_path).resolve()
        if not str(requested).startswith(str(frontend_root_path)):
            raise HTTPException(status_code=403, detail="Access denied")
        if requested.is_file():
            return FileResponse(str(requested))
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))

    logger.info("Frontend static files enabled from %s", _FRONTEND_DIR)
else:
    logger.info("No frontend dist directory found at %s — serving API only", _FRONTEND_DIR)
