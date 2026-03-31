# =============================================================================
# train/Dockerfile
# 训练子系统镜像
# 镜像名：agilestar/ai-train:latest
# 服务端口：8001
#
# CUDA 版本规范：
#   标准版本：CUDA 11.8.0（LTS 版本，强制要求）
#   理由：
#     1. 最佳兼容性：支持 PyTorch 2.0-2.4 全系列
#     2. 生态成熟：所有主流框架均有稳定支持
#     3. 长期维护：CUDA 11.x 系列最后稳定版本
#
#   ⚠️ 不支持其他 CUDA 版本，避免依赖冲突
#   详见：docs/cuda_version_standard.md
# =============================================================================

FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

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
#
# 安装策略（CUDA 11.8 专用）：
#   1. 先从 PyTorch 官方 index 安装 torch/torchvision（cu118 版本）
#   2. 再从清华镜像安装其他依赖
#   3. 验证 CUDA 可用性
#
#   ⚠️ 必须使用 cu118 索引，确保与 CUDA 11.8 匹配
# ---------------------------------------------------------------------------
COPY train/scripts/face_detect/requirements.txt train/scripts/face_detect/requirements.txt
COPY train/scripts/desktop_recapture_detect/requirements.txt train/scripts/desktop_recapture_detect/requirements.txt

RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cu118 \
    && pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r train/scripts/face_detect/requirements.txt \
    -r train/scripts/desktop_recapture_detect/requirements.txt \
    && python3 -c "import torch; import cv2; from PIL import Image; print(f'[OK] PyTorch {torch.__version__} CUDA {torch.version.cuda}, cv2 + Pillow importable')"

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
