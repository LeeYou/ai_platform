# =============================================================================
# test/Dockerfile
# 测试子系统镜像
# 镜像名：agilestar/ai-test:latest
# 服务端口：8002
# =============================================================================

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
# Use Tsinghua mirror for faster downloads in China
COPY test/backend/requirements.txt test/backend/requirements.txt
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r test/backend/requirements.txt

# Frontend build
# Use Taobao npm registry for faster downloads in China
COPY test/frontend/ test/frontend/
RUN cd test/frontend \
    && npm config set registry https://registry.npmmirror.com \
    && npm install \
    && npm run build

# Backend source
COPY test/backend/ test/backend/

ENV PYTHONUNBUFFERED=1 \
    MODELS_ROOT=/workspace/models \
    DATASETS_ROOT=/workspace/datasets

# Ensure log directory exists (volume mount may override at runtime)
RUN mkdir -p /workspace/logs

EXPOSE 8002

WORKDIR /app/test/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
