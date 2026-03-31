# =============================================================================
# train/Dockerfile
# 训练子系统镜像（Docker 构建缓存优化版）
# 镜像名：agilestar/ai-train:latest
# 服务端口：8001
#
# 优化策略：
#   1. 依赖分层：PyTorch、基础库、业务依赖分别安装
#   2. 顺序优化：稳定的层在前，易变的层在后
#   3. BuildKit 缓存：pip 和 npm 缓存挂载
#
# 使用方法：
#   DOCKER_BUILDKIT=1 docker build -t agilestar/ai-train:latest -f train/Dockerfile .
#
# 注意：
#   - 推荐启用 BuildKit 以获得最佳构建性能（运行 source scripts/enable_buildkit.sh）
#   - 旧版 Dockerfile 已备份为 train/Dockerfile.legacy
# =============================================================================

FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

# ---------------------------------------------------------------------------
# Level 0: 系统依赖（很少变化）
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
# Level 1: 核心框架 - PyTorch (2GB, 很少变化)
# 🔑 关键优化：单独一层安装 PyTorch，避免与业务依赖混合
# 使用 BuildKit 缓存挂载加速下载
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    torch==2.4.1 \
    torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cu118

# ---------------------------------------------------------------------------
# Level 2: 框架基础库（偶尔变化）
# 🔑 关键优化：numpy、opencv 等基础库单独一层
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    numpy==1.24.3 \
    opencv-python-headless==4.8.1.78 \
    Pillow==10.0.0 \
    pyyaml==6.0.1 \
    tqdm==4.66.1 \
    scipy==1.11.3

# ---------------------------------------------------------------------------
# Level 2.5: FastAPI 后端依赖（相对稳定）
# ---------------------------------------------------------------------------
COPY train/backend/requirements.txt train/backend/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r train/backend/requirements.txt

# ---------------------------------------------------------------------------
# Level 3: 训练脚本依赖（经常变化）
# 🔑 关键优化：业务特定依赖（ultralytics、onnxslim 等）单独安装
#             即使这些包更新，也不会影响 PyTorch 层的缓存
# ---------------------------------------------------------------------------
COPY train/scripts/face_detect/requirements.txt /tmp/face_detect_req.txt
COPY train/scripts/desktop_recapture_detect/requirements.txt /tmp/desktop_req.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r /tmp/face_detect_req.txt \
    -r /tmp/desktop_req.txt \
    && python3 -c "import torch; import cv2; from PIL import Image; print(f'[OK] PyTorch {torch.__version__} CUDA {torch.version.cuda}, cv2 + Pillow importable')"

# ---------------------------------------------------------------------------
# Level 4: Frontend dependencies（npm 包）
# 🔑 关键优化：只 COPY package*.json，先安装依赖，再 COPY 源码
# ---------------------------------------------------------------------------
COPY train/frontend/package*.json train/frontend/
RUN --mount=type=cache,target=/root/.npm \
    cd train/frontend \
    && npm config set registry https://registry.npmmirror.com \
    && npm ci

# Frontend source and build
COPY train/frontend/ train/frontend/
RUN cd train/frontend && npm run build

# ---------------------------------------------------------------------------
# Level 5: 应用代码（最频繁变化）
# 🔑 放在最后，确保代码变更不影响任何依赖层的缓存
# ---------------------------------------------------------------------------
COPY train/scripts/ train/scripts/
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
