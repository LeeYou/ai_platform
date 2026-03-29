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
RUN cd prod/frontend && npm install && npm run build

# ─── Stage 2: Runtime ───────────────────────────────────────────────────────
FROM ubuntu:22.04

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
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------------------------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------------------------
COPY prod/web_service/requirements.txt prod/web_service/requirements.txt
RUN pip install --no-cache-dir -r prod/web_service/requirements.txt

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
RUN mkdir -p /app/models /app/libs /app/licenses /mnt/ai_platform /mnt/ai_platform/pipelines

# ---------------------------------------------------------------------------
# Runtime environment
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    MOUNT_ROOT=/mnt/ai_platform \
    BUILTIN_ROOT=/app \
    AI_BACKEND=auto \
    LOG_LEVEL=info \
    UVICORN_WORKERS=2

EXPOSE 8080

WORKDIR /app/prod/web_service
ENTRYPOINT ["/app/docker-entrypoint.sh"]
