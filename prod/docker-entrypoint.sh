#!/usr/bin/env bash
# =============================================================================
# docker-entrypoint.sh — 生产容器启动入口
# 检测 GPU 可用性，设置 AI_BACKEND 环境变量，启动 FastAPI 服务
#
# Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
# =============================================================================

set -e

echo "[ai-prod] Starting AI Production Service..."
echo "[ai-prod] Server time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------
if nvidia-smi > /dev/null 2>&1; then
    echo "[ai-prod] GPU detected — using ONNXRuntime CUDA backend"
    export AI_BACKEND="${AI_BACKEND:-onnxruntime-gpu}"
else
    echo "[ai-prod] No GPU detected — using CPU backend"
    export AI_BACKEND="${AI_BACKEND:-onnxruntime-cpu}"
fi

# ---------------------------------------------------------------------------
# Resource path resolution (mount > built-in)
# ---------------------------------------------------------------------------
if [ -d "/mnt/ai_platform/models" ]; then
    echo "[ai-prod] Using mounted models:   /mnt/ai_platform/models"
else
    echo "[ai-prod] Using built-in models:  /app/models"
fi

if [ -d "/mnt/ai_platform/licenses" ]; then
    export AI_LICENSE_PATH="/mnt/ai_platform/licenses/license.bin"
    echo "[ai-prod] Using mounted license:  ${AI_LICENSE_PATH}"
else
    export AI_LICENSE_PATH="${AI_LICENSE_PATH:-/app/licenses/license.bin}"
    echo "[ai-prod] Using built-in license: ${AI_LICENSE_PATH}"
fi

# ---------------------------------------------------------------------------
# Start service
# ---------------------------------------------------------------------------
echo "[ai-prod] Starting uvicorn on 0.0.0.0:8080..."
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --workers "${UVICORN_WORKERS:-2}" \
    --log-level "${LOG_LEVEL:-info}"
