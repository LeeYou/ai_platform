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
    libgl1-mesa-glx \
    libglib2.0-0 \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY test/backend/requirements.txt test/backend/requirements.txt
RUN pip install --no-cache-dir -r test/backend/requirements.txt

# Frontend build
COPY test/frontend/ test/frontend/
RUN cd test/frontend && npm install && npm run build

# Backend source
COPY test/backend/ test/backend/

ENV PYTHONUNBUFFERED=1 \
    MODELS_ROOT=/workspace/models \
    DATASETS_ROOT=/workspace/datasets

EXPOSE 8002

WORKDIR /app/test/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
