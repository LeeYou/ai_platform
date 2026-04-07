"""Build Management API — trigger CMake builds, stream build logs.

Provides a web UI for selecting AI capabilities, binding customer key pairs
(via license service proxy), and compiling customer-specific SO libraries
with the trusted public-key fingerprint compiled in.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

import asyncio
import hashlib
import hmac
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from glob import glob
from logging.handlers import RotatingFileHandler
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}

CPP_SOURCE_DIR = os.getenv("CPP_SOURCE_DIR", "/app/cpp")
BUILD_OUTPUT_DIR = os.getenv("BUILD_OUTPUT_DIR", "/workspace/libs/linux_x86_64")
BUILD_LOG_DIR = "./data/build_logs"
BUILD_STATE_FILE = "./data/build_jobs.json"
LOG_DIR = os.getenv("LOG_DIR", "./data/build_logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LICENSE_SERVICE_URL = os.getenv("LICENSE_SERVICE_URL", "http://license:8003")
TRAIN_SERVICE_URL = os.getenv("TRAIN_SERVICE_URL", "http://train:8001")
MODELS_ROOT = os.getenv("MODELS_ROOT", "/workspace/models")
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

ALLOWED_BUILD_TYPES = {"Debug", "Release", "RelWithDebInfo", "MinSizeRel"}
# CMake -D args must match: -DVARNAME=VALUE (alphanumeric + underscore/dot/dash)
CMAKE_ARG_RE = re.compile(r"^-D[A-Za-z_][A-Za-z0-9_]*(=[\w./-]*)?$")
TRUTHY_CMAKE_VALUES = {"1", "ON", "TRUE", "YES"}
RUNTIME_GPU_SOURCE_TOKENS = (
    "AppendExecutionProvider_CUDA",
    "SessionOptionsAppendExecutionProvider_CUDA",
    "OrtCUDAProviderOptions",
)
COMPILE_GPU_SOURCE_TOKENS = (
    "NvInfer",
    "nvinfer",
    "cuda_runtime.h",
    "__global__",
    "cudaMalloc",
)
COMPILE_GPU_CMAKE_FLAGS = {
    "ENABLE_TENSORRT": "TensorRT",
    "ENABLE_CUDA_KERNELS": "CUDA kernels",
}


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
    _load_jobs()
    _mark_interrupted_builds_failed()
    logger.info("Build Management service started")
    yield
    _persist_jobs()
    logger.info("Build Management service stopped")


app = FastAPI(
    title="Build Management API",
    version="1.0.0",
    description="Trigger CMake builds and stream build logs for AI capability SO",
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
# Schemas
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    capability: str           # e.g. "recapture_detect"
    platform: str = "linux_x86_64"
    build_type: str = "Release"
    key_pair_id: Optional[int] = None  # binds customer key pair, auto-computes fingerprint
    trusted_pubkey_sha256: Optional[str] = None  # or pass fingerprint directly
    extra_cmake_args: Optional[list[str]] = None
    mark_as_current: bool = True


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
    model_version: Optional[str] = None
    artifact_dir: Optional[str] = None
    error_msg: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _persist_jobs() -> None:
    os.makedirs(os.path.dirname(BUILD_STATE_FILE) or ".", exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="build_jobs_",
        suffix=".json",
        dir=os.path.dirname(BUILD_STATE_FILE) or ".",
    )
    try:
        import json
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(list(_jobs.values()), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, BUILD_STATE_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _load_jobs() -> None:
    if not os.path.exists(BUILD_STATE_FILE):
        return
    try:
        import json
        with open(BUILD_STATE_FILE, encoding="utf-8") as f:
            jobs = json.load(f)
        _jobs.clear()
        for job in jobs:
            if isinstance(job, dict) and job.get("job_id"):
                _jobs[job["job_id"]] = job
    except Exception as exc:
        logger.warning("Failed to load persisted build jobs from %s: %s", BUILD_STATE_FILE, exc)


def _mark_interrupted_builds_failed() -> None:
    changed = False
    finished_at = datetime.now(timezone.utc).isoformat()
    for job in _jobs.values():
        if job.get("status") in {"pending", "running"}:
            job["status"] = "failed"
            job["error_msg"] = "Service restarted before build completed"
            job["finished_at"] = finished_at
            changed = True
    if changed:
        _persist_jobs()


def _resolve_model_version(capability: str) -> str | None:
    if not os.path.isdir(MODELS_ROOT):
        return None

    try:
        import json
        versions: dict[str, str] = {}
        for entry in os.listdir(MODELS_ROOT):
            safe_entry = _safe_path_component(entry, "")
            if not safe_entry or safe_entry != entry:
                continue
            manifest_path = os.path.join(MODELS_ROOT, entry, "current", "manifest.json")
            if not os.path.exists(manifest_path):
                continue
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
                version = str(manifest.get("model_version", "")).strip()
                if version:
                    versions[entry] = _safe_path_component(version, "unversioned")
            except Exception as exc:
                logger.warning("Failed to read model version for %s: %s", entry, exc)
        return versions.get(capability)
    except Exception as exc:
        logger.warning("Failed to scan model versions from %s: %s", MODELS_ROOT, exc)
        return None


def _safe_path_component(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._-")
    return cleaned or fallback


def _artifact_dir_for_job(job: dict) -> str:
    artifact_dir = job.get("artifact_dir")
    if artifact_dir:
        return artifact_dir
    model_version = _safe_path_component(job.get("model_version") or "unversioned", "unversioned")
    capability = _safe_path_component(job["capability"], "capability")
    job_id = _safe_path_component(job["job_id"], "job")
    return os.path.join(BUILD_OUTPUT_DIR, capability, model_version, job_id)


def _run_command_output(args: list[str], cwd: str | None = None) -> str:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (completed.stdout or completed.stderr or "").strip().splitlines()
        return output[0].strip() if output else ""
    except Exception:
        return ""


def _cmake_flag_enabled(extra_args: list[str] | None, name: str) -> bool:
    bare = f"-D{name}"
    prefix = f"-D{name}="
    for arg in extra_args or []:
        if arg == bare:
            return True
        if arg.startswith(prefix):
            return arg.split("=", 1)[1].strip().upper() in TRUTHY_CMAKE_VALUES
    return False


def _capability_source_files(capability: str) -> list[str]:
    safe_capability = _safe_path_component(capability, "")
    if not safe_capability or safe_capability != capability:
        return []
    cap_root = os.path.realpath(os.path.join(CPP_SOURCE_DIR, "capabilities"))
    cap_dir = os.path.realpath(os.path.join(cap_root, safe_capability))
    if cap_dir != os.path.join(cap_root, safe_capability) or not os.path.isdir(cap_dir):
        return []

    result: list[str] = []
    for root, _dirs, files in os.walk(cap_dir):
        root = os.path.realpath(root)
        if not root.startswith(cap_dir + os.sep) and root != cap_dir:
            continue
        for name in files:
            if name.endswith((".c", ".cc", ".cpp", ".cxx", ".cu", ".h", ".hpp", ".hxx", ".cuh", ".txt")):
                path = os.path.realpath(os.path.join(root, name))
                if path.startswith(cap_dir + os.sep):
                    result.append(path)
    return result


def _capability_supports_runtime_gpu(capability: str) -> bool:
    for path in _capability_source_files(capability):
        if not path.endswith((".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx")):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue
        if any(token in content for token in RUNTIME_GPU_SOURCE_TOKENS):
            return True
    return False


def _capability_requires_compile_gpu_toolchain(capability: str) -> bool:
    for path in _capability_source_files(capability):
        if path.endswith((".cu", ".cuh")):
            return True
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue
        if any(token in content for token in COMPILE_GPU_SOURCE_TOKENS):
            return True
    return False


def _probe_builder_environment() -> dict:
    cuda_home = "/usr/local/cuda"
    tensorrt_include_candidates = (
        "/usr/include/NvInfer.h",
        "/usr/local/tensorrt/include/NvInfer.h",
        "/usr/local/TensorRT/include/NvInfer.h",
        "/opt/tensorrt/include/NvInfer.h",
    )
    tensorrt_library_patterns = (
        "/usr/lib*/**/libnvinfer.so*",
        "/usr/local/tensorrt/lib*/libnvinfer.so*",
        "/usr/local/TensorRT/lib*/libnvinfer.so*",
        "/opt/tensorrt/lib*/libnvinfer.so*",
    )
    ort_cuda_provider = "/usr/local/lib/libonnxruntime_providers_cuda.so"

    nvcc_path = shutil.which("nvcc") or ""
    tensorrt_include = next((path for path in tensorrt_include_candidates if os.path.exists(path)), "")
    tensorrt_library = ""
    for pattern in tensorrt_library_patterns:
        matches = sorted(glob(pattern, recursive=True))
        if matches:
            tensorrt_library = matches[0]
            break

    onnxruntime_package = "gpu" if os.path.exists(ort_cuda_provider) else "cpu"
    cuda_toolkit_available = bool(nvcc_path and os.path.isdir(cuda_home))
    tensorrt_available = bool(tensorrt_include and tensorrt_library)

    supports_compile_time_gpu_features = []
    if cuda_toolkit_available:
        supports_compile_time_gpu_features.append("ENABLE_CUDA_KERNELS")
    if cuda_toolkit_available and tensorrt_available and onnxruntime_package == "gpu":
        supports_compile_time_gpu_features.append("ENABLE_TENSORRT")

    return {
        "builder_image": os.getenv("BUILDER_IMAGE", os.getenv("HOSTNAME", "unknown")),
        "builder_toolchain_profile": os.getenv("BUILDER_TOOLCHAIN_PROFILE", "cpu-ort"),
        "cmake_version": _run_command_output(["cmake", "--version"]),
        "compiler": _run_command_output(["c++", "--version"]) or _run_command_output(["g++", "--version"]),
        "cuda_home": cuda_home,
        "cuda_home_exists": os.path.isdir(cuda_home),
        "cuda_toolkit_available": cuda_toolkit_available,
        "nvcc_path": nvcc_path,
        "tensorrt_available": tensorrt_available,
        "tensorrt_include": tensorrt_include,
        "tensorrt_library": tensorrt_library,
        "onnxruntime_root": os.getenv("ONNXRUNTIME_ROOT", "/usr/local"),
        "onnxruntime_package": onnxruntime_package,
        "onnxruntime_cuda_provider_library": ort_cuda_provider if os.path.exists(ort_cuda_provider) else "",
        "supports_compile_time_gpu_features": supports_compile_time_gpu_features,
    }


def _build_gpu_profile(capability: str, extra_args: list[str] | None) -> dict:
    compile_gpu_features = [
        flag_name for flag_name in COMPILE_GPU_CMAKE_FLAGS
        if _cmake_flag_enabled(extra_args, flag_name)
    ]
    runtime_gpu_capable = _capability_supports_runtime_gpu(capability)
    compile_time_gpu_required = bool(compile_gpu_features) or _capability_requires_compile_gpu_toolchain(capability)

    if compile_time_gpu_required:
        compile_gpu_mode = "cuda_toolchain_required"
    elif runtime_gpu_capable:
        compile_gpu_mode = "runtime_only"
    else:
        compile_gpu_mode = "cpu_only"

    return {
        "runtime_gpu_capable": runtime_gpu_capable,
        "compile_gpu_features": compile_gpu_features,
        "compile_time_gpu_required": compile_time_gpu_required,
        "compile_gpu_mode": compile_gpu_mode,
        "legacy_build_gpu_requested": _cmake_flag_enabled(extra_args, "BUILD_GPU"),
    }


def _validate_build_environment(capability: str, extra_args: list[str] | None) -> tuple[dict, dict]:
    builder_env = _probe_builder_environment()
    gpu_profile = _build_gpu_profile(capability, extra_args)

    missing: list[str] = []
    compile_gpu_features = set(gpu_profile["compile_gpu_features"])

    if "ENABLE_CUDA_KERNELS" in compile_gpu_features and not builder_env["cuda_toolkit_available"]:
        missing.append("CUDA Toolkit (nvcc + /usr/local/cuda)")

    if "ENABLE_TENSORRT" in compile_gpu_features:
        if not builder_env["cuda_toolkit_available"]:
            missing.append("CUDA Toolkit (TensorRT build requires CUDA Toolkit)")
        if builder_env["onnxruntime_package"] != "gpu":
            missing.append("ONNX Runtime GPU package")
        if not builder_env["tensorrt_available"]:
            missing.append("TensorRT headers/libs")

    if missing:
        missing_text = "，".join(dict.fromkeys(missing))
        requested = ", ".join(sorted(COMPILE_GPU_CMAKE_FLAGS[name] for name in compile_gpu_features))
        raise HTTPException(
            status_code=400,
            detail=(
                f"{capability} 请求了编译期 GPU 特性（{requested}），"
                f"但当前 builder 缺少：{missing_text}。"
                "请改用 GPU builder 镜像或移除对应编译期开关；"
                "仅运行时 GPU 优先的能力无需传 -DBUILD_GPU=ON。"
            ),
        )

    return builder_env, gpu_profile


def _write_build_info(job: dict, req: BuildRequest, artifact_dir: str) -> None:
    import json

    builder_env, gpu_profile = _validate_build_environment(job["capability"], req.extra_cmake_args or [])
    build_info = {
        "capability": job["capability"],
        "version": job.get("model_version") or "unversioned",
        "target_arch": req.platform,
        "build_type": req.build_type,
        "gpu_enabled": gpu_profile["runtime_gpu_capable"],
        "runtime_gpu_capable": gpu_profile["runtime_gpu_capable"],
        "compile_gpu_mode": gpu_profile["compile_gpu_mode"],
        "compile_gpu_features": gpu_profile["compile_gpu_features"],
        "build_gpu_toolchain": builder_env["cuda_toolkit_available"],
        "builder_toolchain_profile": builder_env["builder_toolchain_profile"],
        "builder_image": builder_env["builder_image"],
        "cmake_version": builder_env["cmake_version"],
        "compiler": builder_env["compiler"],
        "onnxruntime_package": builder_env["onnxruntime_package"],
        "cuda_toolkit_available": builder_env["cuda_toolkit_available"],
        "tensorrt_available": builder_env["tensorrt_available"],
        "built_at": datetime.now(timezone.utc).isoformat(),
        "built_by": builder_env["builder_image"],
        "git_commit": _run_command_output(["git", "rev-parse", "--short", "HEAD"], cwd=os.path.dirname(CPP_SOURCE_DIR)),
        "trusted_pubkey_sha256": job.get("trusted_pubkey_sha256"),
        "job_id": job["job_id"],
    }
    with open(os.path.join(artifact_dir, "build_info.json"), "w", encoding="utf-8") as f:
        json.dump(build_info, f, ensure_ascii=False, indent=2)


async def _get_capability_diagnostics() -> dict:
    cap_dir = os.path.join(CPP_SOURCE_DIR, "capabilities")
    source_caps = []
    if os.path.isdir(cap_dir):
        source_caps = sorted(
            d for d in os.listdir(cap_dir)
            if os.path.isdir(os.path.join(cap_dir, d)) and not d.startswith(".")
        )

    train_caps = []
    train_service_reachable = False
    train_service_status_code = None
    train_service_error = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            payload = None
            last_response = None
            for path in ("/api/v1/capabilities/", "/api/v1/capabilities"):
                resp = await client.get(f"{TRAIN_SERVICE_URL}{path}", follow_redirects=True)
                last_response = resp
                train_service_status_code = resp.status_code
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                payload = resp.json()
                break

            if payload is None:
                if last_response is not None:
                    last_response.raise_for_status()
                train_service_error = "Training service capability endpoint not found"
            elif isinstance(payload, list):
                train_caps = [cap.get("name", "") for cap in payload if isinstance(cap, dict) and cap.get("name")]
                train_service_reachable = True
            else:
                train_service_error = f"Unexpected response shape: {type(payload).__name__}"
    except httpx.TimeoutException:
        train_service_error = "Training service request timed out"
    except httpx.HTTPStatusError as exc:
        train_service_error = f"Training service returned HTTP {exc.response.status_code}"
    except httpx.RequestError:
        train_service_error = "Training service unreachable"
    except httpx.HTTPError:
        train_service_error = "Training service request failed"

    available = sorted(cap for cap in train_caps if cap in set(source_caps))
    return {
        "train_service_url": TRAIN_SERVICE_URL,
        "train_service_reachable": train_service_reachable,
        "train_service_status_code": train_service_status_code,
        "train_service_error": train_service_error,
        "cpp_source_dir": CPP_SOURCE_DIR,
        "capability_source_dir": cap_dir,
        "capability_source_dir_exists": os.path.isdir(cap_dir),
        "source_capabilities": source_caps,
        "train_capabilities": sorted(train_caps),
        "available_capabilities": available,
        "models_root": MODELS_ROOT,
        "models_root_exists": os.path.isdir(MODELS_ROOT),
    }


def _update_current_symlink(job: dict) -> None:
    capability_root = os.path.join(BUILD_OUTPUT_DIR, _safe_path_component(job["capability"], "capability"))
    current_link = os.path.join(capability_root, "current")
    target_dir = _artifact_dir_for_job(job)
    relative_target = os.path.relpath(target_dir, capability_root)

    os.makedirs(capability_root, exist_ok=True)
    if os.path.lexists(current_link):
        if os.path.isdir(current_link) and not os.path.islink(current_link):
            logger.warning("Build %s: current path exists as directory, skip symlink update: %s", job["job_id"], current_link)
            return
        os.unlink(current_link)
    os.symlink(relative_target, current_link)
    logger.info("Build %s: updated current symlink to %s", job["job_id"], relative_target)


def _create_lib_symlinks(artifact_dir: str, job_id: str) -> None:
    """Create standard library symlinks (libfoo.so -> libfoo.so.1 -> libfoo.so.1.0.0)."""
    lib_dir = os.path.join(artifact_dir, "lib")
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
    job["error_msg"] = None
    _persist_jobs()
    logger.info("Build %s started: capability=%s platform=%s", job_id, req.capability, req.platform)

    build_dir = f"/tmp/build_{job_id}"
    os.makedirs(build_dir, exist_ok=True)
    artifact_dir = _artifact_dir_for_job(job)
    os.makedirs(artifact_dir, exist_ok=True)
    builder_env, gpu_profile = _validate_build_environment(job["capability"], req.extra_cmake_args or [])

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
        "--prefix", artifact_dir,
    ]

    try:
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(
                "# Build preflight\n"
                f"# builder_image={builder_env['builder_image']}\n"
                f"# builder_toolchain_profile={builder_env['builder_toolchain_profile']}\n"
                f"# runtime_gpu_capable={gpu_profile['runtime_gpu_capable']}\n"
                f"# compile_gpu_mode={gpu_profile['compile_gpu_mode']}\n"
                f"# compile_gpu_features={','.join(gpu_profile['compile_gpu_features']) or '(none)'}\n"
                f"# onnxruntime_package={builder_env['onnxruntime_package']}\n"
                f"# cuda_toolkit_available={builder_env['cuda_toolkit_available']}\n"
                f"# tensorrt_available={builder_env['tensorrt_available']}\n"
            )
            if gpu_profile["legacy_build_gpu_requested"]:
                lf.write(
                    "# note: -DBUILD_GPU=ON is compatibility-only; "
                    "runtime GPU fallback is auto-detected by the capability.\n"
                )
            lf.flush()
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
                    job["error_msg"] = f"Build command failed: {cmd_display}"
                    job["finished_at"] = datetime.now(timezone.utc).isoformat()
                    _persist_jobs()
                    logger.error("Build %s failed at command: %s (exit code %s)", job_id, cmd_display, proc.returncode)
                    return

        # Create library symlinks after successful build
        _create_lib_symlinks(artifact_dir, job_id)
        _write_build_info(job, req, artifact_dir)
        if req.mark_as_current:
            _update_current_symlink(job)

        job["status"] = "done"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _persist_jobs()
        logger.info("Build %s completed successfully", job_id)
    except Exception as exc:
        job["status"] = "failed"
        job["error_msg"] = str(exc)
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _persist_jobs()
        logger.error("Build %s failed during post-processing: %s", job_id, exc, exc_info=True)
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


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

    _validate_build_environment(req.capability, req.extra_cmake_args or [])

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
    model_version = _resolve_model_version(req.capability) or "unversioned"
    safe_capability = _safe_path_component(req.capability, "capability")
    safe_job_id = _safe_path_component(job_id, "job")
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
        "model_version": model_version,
        "artifact_dir": os.path.join(BUILD_OUTPUT_DIR, safe_capability, model_version, safe_job_id),
        "error_msg": None,
    }
    _jobs[job_id] = job
    _persist_jobs()
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
    token = websocket.query_params.get("token", "").strip()
    if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        await websocket.close(code=4401)
        return
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
    diagnostics = await _get_capability_diagnostics()
    if not diagnostics["train_service_reachable"]:
        logger.error(
            "Failed to fetch capabilities from training service: %s",
            diagnostics["train_service_error"] or "unknown error",
        )
    logger.info(
        "Returning %d buildable capabilities (from training API + source): %s",
        len(diagnostics["available_capabilities"]),
        diagnostics["available_capabilities"],
    )
    return diagnostics["available_capabilities"]


@app.get("/api/v1/capabilities/diagnostics", tags=["capabilities"])
async def capability_diagnostics():
    return await _get_capability_diagnostics()


@app.get("/api/v1/builder/diagnostics", tags=["builder"])
def builder_diagnostics():
    return _probe_builder_environment()


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
    artifact_dir = _artifact_dir_for_job(_jobs[job_id])
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
    artifact_dir = os.path.realpath(_artifact_dir_for_job(_jobs[job_id]))
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
    model_version = job.get("model_version") or "unversioned"
    artifact_dir = os.path.realpath(_artifact_dir_for_job(job))

    if not os.path.isdir(artifact_dir):
        raise HTTPException(status_code=404, detail="No artifacts found for this build")

    # Create temporary tar.gz file
    temp_fd, temp_path = tempfile.mkstemp(suffix=".tar.gz", prefix=f"build_{job_id}_")
    try:
        os.close(temp_fd)
        with tarfile.open(temp_path, "w:gz") as tar:
            tar.add(artifact_dir, arcname=os.path.join(cap, model_version, job_id))

        package_name = f"{cap}_{model_version}_{job_id[:8]}.tar.gz"
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
