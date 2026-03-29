# =============================================================================
# train/Dockerfile
# 训练子系统镜像
# 镜像名：agilestar/ai-train:latest
# 服务端口：8001
#
# CUDA 版本说明：
#   默认使用 CUDA 11.8（兼容性最广，支持 PyTorch 2.x 所有版本）
#   如需 CUDA 12.x，构建时指定：
#     docker build --build-arg CUDA_BASE_IMAGE=nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04 ...
#
# 支持的基础镜像（已验证）：
#   - nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04  (默认，推荐)
#   - nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04
# =============================================================================

ARG CUDA_BASE_IMAGE=nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04
FROM ${CUDA_BASE_IMAGE}

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3-pip \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node.js 18 (for frontend build)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Ensure python3 → python3.10
RUN ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

# ---------------------------------------------------------------------------
# Python backend dependencies (cached layer)
# ---------------------------------------------------------------------------
COPY train/backend/requirements.txt train/backend/requirements.txt
RUN pip install --no-cache-dir -r train/backend/requirements.txt

# ---------------------------------------------------------------------------
# Frontend build
# ---------------------------------------------------------------------------
COPY train/frontend/ train/frontend/
RUN cd train/frontend && npm install && npm run build

# ---------------------------------------------------------------------------
# Training scripts dependencies (optional — torch is large)
# ---------------------------------------------------------------------------
COPY train/scripts/ train/scripts/
RUN pip install --no-cache-dir -r train/scripts/face_detect/requirements.txt || true

# ---------------------------------------------------------------------------
# Backend source
# ---------------------------------------------------------------------------
COPY train/backend/ train/backend/

# ---------------------------------------------------------------------------
# Runtime environment
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    DATASETS_ROOT=/workspace/datasets \
    MODELS_ROOT=/workspace/models \
    REDIS_URL=redis://redis:6379/0

# Ensure log directory exists (volume mount may override at runtime)
RUN mkdir -p /workspace/logs

EXPOSE 8001

WORKDIR /app/train/backend

CMD ["sh", "-c", \
    "celery -A tasks.celery_app worker --loglevel=info --detach && \
     uvicorn main:app --host 0.0.0.0 --port 8001"]
