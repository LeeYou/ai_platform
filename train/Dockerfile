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
    # Runtime libraries for opencv-python-headless
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    # Additional OpenCV dependencies
    libgl1 \
    libgomp1 \
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
# Use Tsinghua mirror for faster downloads in China
# ---------------------------------------------------------------------------
COPY train/backend/requirements.txt train/backend/requirements.txt
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r train/backend/requirements.txt

# ---------------------------------------------------------------------------
# Training scripts requirements (cached layer — copy only requirements first)
# Install BEFORE frontend build so frontend code changes don't invalidate
# the heavy ML package layer (~2 GB for torch, etc.).
# Use Tsinghua mirror for faster downloads in China
# ---------------------------------------------------------------------------
COPY train/scripts/face_detect/requirements.txt train/scripts/face_detect/requirements.txt
COPY train/scripts/desktop_recapture_detect/requirements.txt train/scripts/desktop_recapture_detect/requirements.txt

RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r train/scripts/face_detect/requirements.txt \
    -r train/scripts/desktop_recapture_detect/requirements.txt \
    && python3 -c "import cv2; from PIL import Image; print('[OK] cv2 + Pillow importable')"

# ---------------------------------------------------------------------------
# Frontend build
# Use Taobao npm registry for faster downloads in China
# ---------------------------------------------------------------------------
COPY train/frontend/ train/frontend/
RUN cd train/frontend \
    && npm config set registry https://registry.npmmirror.com \
    && npm install \
    && npm run build

# ---------------------------------------------------------------------------
# Training scripts source
# ---------------------------------------------------------------------------
COPY train/scripts/ train/scripts/

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
