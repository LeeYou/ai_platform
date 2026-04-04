# =============================================================================
# test/Dockerfile
# 测试子系统镜像
# 镜像名：agilestar/ai-test:latest
# 服务端口：8002
# =============================================================================

# Stage 1 – build Vue3 / Vite frontend.
# vite@5 and @vitejs/plugin-vue@5 require Node.js >= 18; use the official
# node:20-slim image so the correct engine is always available regardless of
# what the host OS package manager provides.
FROM node:20-slim AS frontend-build

WORKDIR /app
COPY test/frontend/ test/frontend/
# Use Taobao npm registry for faster downloads in China
RUN cd test/frontend \
    && npm config set registry https://registry.npmmirror.com \
    && npm install \
    && npm run build

# =============================================================================
# Stage 2 – runtime image
# Use the same CUDA runtime base as the prod image so that onnxruntime-gpu can
# find the required CUDA / cuDNN shared libraries for GPU-accelerated inference.
# =============================================================================
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    curl \
    libgl1 \
    libglib2.0-0 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
# Use Tsinghua mirror for faster downloads in China
COPY test/backend/requirements.txt test/backend/requirements.txt
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r test/backend/requirements.txt

# Copy pre-built frontend assets from the frontend-build stage.
# Node.js and npm are NOT present in the final image, keeping it lean.
COPY --from=frontend-build /app/test/frontend/dist/ test/frontend/dist/

# Backend source
COPY test/backend/ test/backend/

ENV PYTHONUNBUFFERED=1 \
    MODELS_ROOT=/workspace/models \
    DATASETS_ROOT=/workspace/datasets \
    CUDA_HOME=/usr/local/cuda \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/nvidia/lib64:${LD_LIBRARY_PATH}

# Ensure log directory exists (volume mount may override at runtime)
RUN mkdir -p /workspace/logs

EXPOSE 8002

WORKDIR /app/test/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
