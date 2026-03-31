FROM python:3.11-slim AS frontend-builder

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY license/frontend/ license/frontend/
RUN cd license/frontend \
    && npm config set registry https://registry.npmmirror.com \
    && npm install \
    && npm run build

# ─── Runtime image ─────────────────────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY license/backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

COPY license/backend/ backend/
COPY --from=frontend-builder /app/license/frontend/dist frontend/dist

# Ensure log directory exists (volume mount may override at runtime)
RUN mkdir -p /app/logs

EXPOSE 8003
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
