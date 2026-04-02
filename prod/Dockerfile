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

# ─── Stage 2: Runtime (GPU-first with CPU fallback) ────────────────────────
# Use NVIDIA CUDA Runtime base image to enable GPU acceleration
# This provides CUDA Runtime libraries + cuDNN for ONNXRuntime GPU inference
# CPU-only fallback works automatically if no GPU is detected
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    libgl1-mesa-glx \
    libglib2.0-0 \
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
    -r prod/web_service/requirements.txt

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
