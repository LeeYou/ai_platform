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
# Production service must ship a fixed CUDA 11.8 runtime so the delivered
# customer image has a consistent GPU-capable environment.
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
# Keep this aligned with the ONNX Runtime version used by ai-builder so the
# deployed capability plugins and bundled provider shared libraries stay ABI-compatible.
ARG ONNXRUNTIME_VERSION=1.18.1
ARG ONNXRUNTIME_PACKAGE=onnxruntime-linux-x64-gpu

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
    -r prod/web_service/requirements.txt
RUN python3 - <<'PY'
import cryptography
print("cryptography:", cryptography.__version__)
PY
RUN curl -fsSL \
    "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/${ONNXRUNTIME_PACKAGE}-${ONNXRUNTIME_VERSION}.tgz" \
    -o /tmp/ort.tgz \
    && tar -xzf /tmp/ort.tgz -C /usr/local --strip-components=1 \
    && rm /tmp/ort.tgz
RUN ldconfig \
    && ldconfig -p | grep -q "libcublasLt.so.11" \
    && ldconfig -p | grep -q "libcudnn.so.8"

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
    CUDA_HOME=/usr/local/cuda \
    ONNXRUNTIME_ROOT=/usr/local \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/nvidia/lib64:/usr/local/lib:${LD_LIBRARY_PATH} \
    UVICORN_WORKERS=2 \
    TZ=Asia/Shanghai

EXPOSE 8080

WORKDIR /app/prod/web_service
ENTRYPOINT ["/app/docker-entrypoint.sh"]
