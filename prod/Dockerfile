# =============================================================================
# prod/Dockerfile
# 生产交付镜像
# 镜像名：agilestar/ai-prod:latest
# 服务端口：8080
# 两阶段构建：Node.js 编译前端 + Python 运行后端
# =============================================================================

# ─── Stage 1: Frontend builder ──────────────────────────────────────────────
FROM node:18-slim AS frontend-builder

WORKDIR /app
COPY prod/frontend/ prod/frontend/
RUN cd prod/frontend \
    && npm config set registry https://registry.npmmirror.com \
    && npm install \
    && npm run build

# ─── Stage 2: Runtime ──────────────────────────────────────────────────────
# Production service uses CPU-only ONNX Runtime (no CUDA needed in container)
# GPU acceleration is handled by compiled SO libraries (built with CUDA 11.8 support)
# The SO files detect GPU availability at runtime and fall back to CPU if needed
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ARG ONNXRUNTIME_GPU_VERSION=1.18.1

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    libgl1-mesa-glx \
    libglib2.0-0 \
    openssl \
    curl \
    ca-certificates \
    tzdata \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------------------------------------------------------------------------
# Python dependencies
# Use Tsinghua mirror for faster downloads in China
# ---------------------------------------------------------------------------
COPY prod/web_service/requirements.txt prod/web_service/requirements.txt
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r prod/web_service/requirements.txt \
    && pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    onnxruntime-gpu==${ONNXRUNTIME_GPU_VERSION}
RUN python3 - <<'PY'
import pathlib
import shutil
import site

copied = set()
dest_dir = pathlib.Path("/usr/local/lib")
dest_dir.mkdir(parents=True, exist_ok=True)
search_roots = []

for candidate in site.getsitepackages() + [site.getusersitepackages()]:
    if candidate and candidate not in search_roots:
        search_roots.append(candidate)

for root in search_roots:
    capi_dir = pathlib.Path(root) / "onnxruntime" / "capi"
    if not capi_dir.is_dir():
        continue
    for source_path in capi_dir.glob("libonnxruntime*.so*"):
        target_path = dest_dir / source_path.name
        if target_path.name in copied:
            continue
        shutil.copy2(source_path, target_path)
        copied.add(target_path.name)

if not copied:
    raise SystemExit("Failed to locate ONNX Runtime shared libraries after installing onnxruntime-gpu")

print("Copied ONNX Runtime shared libraries:", ", ".join(sorted(copied)))
PY
RUN ldconfig

# ---------------------------------------------------------------------------
# Web service source
# ---------------------------------------------------------------------------
COPY prod/web_service/ prod/web_service/
COPY prod/docker-entrypoint.sh docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh

# ---------------------------------------------------------------------------
# Frontend static files
# ---------------------------------------------------------------------------
COPY --from=frontend-builder /app/prod/frontend/dist prod/frontend/dist

# ---------------------------------------------------------------------------
# Default resource directories (overridable via volume mounts)
# ---------------------------------------------------------------------------
# IMPORTANT: Production service requires libai_runtime.so and capability SO files
# These must be compiled using the ai-builder service (see docs/design/build_service.md)
# The production image also ships the matching ONNX Runtime shared libraries
# required by capability SOs (for example libonnxruntime.so.1.18.1).
# and placed in either:
#   - Built-in path: /app/libs/
#   - Mount path:    /mnt/ai_platform/libs/
# Models must be trained/exported and placed in:
#   - Built-in path: /app/models/
#   - Mount path:    /mnt/ai_platform/models/
RUN mkdir -p /app/models /app/libs /app/licenses /mnt/ai_platform /mnt/ai_platform/pipelines

# ---------------------------------------------------------------------------
# Runtime environment
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    MOUNT_ROOT=/mnt/ai_platform \
    BUILTIN_ROOT=/app \
    AI_BACKEND=auto \
    LOG_LEVEL=info \
    UVICORN_WORKERS=2 \
    TZ=Asia/Shanghai

EXPOSE 8080

WORKDIR /app/prod/web_service
ENTRYPOINT ["/app/docker-entrypoint.sh"]
