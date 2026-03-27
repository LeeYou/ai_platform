#!/usr/bin/env bash
# =============================================================================
# scripts/build_and_push.sh
# 构建所有子系统 Docker 镜像并推送到镜像仓库
#
# 用法：
#   ./scripts/build_and_push.sh [REGISTRY] [VERSION]
#
# 示例：
#   ./scripts/build_and_push.sh registry.agilestar.cn/ai-platform 1.0.0
#
# Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
# =============================================================================

set -euo pipefail

REGISTRY="${1:-agilestar}"
VERSION="${2:-latest}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "============================================================"
echo " AI Platform Build & Push"
echo " Registry : ${REGISTRY}"
echo " Version  : ${VERSION}"
echo " Root     : ${REPO_ROOT}"
echo "============================================================"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

build_and_push() {
    local name="$1"
    local dockerfile="$2"
    local tag="${REGISTRY}/${name}:${VERSION}"
    local tag_latest="${REGISTRY}/${name}:latest"

    echo ""
    echo "---- Building ${name} ----"
    docker build \
        -f "${REPO_ROOT}/${dockerfile}" \
        -t "${tag}" \
        -t "${tag_latest}" \
        "${REPO_ROOT}"

    echo "---- Pushing ${name} ----"
    docker push "${tag}"
    docker push "${tag_latest}"
    echo "---- Done: ${tag} ----"
}

# ---------------------------------------------------------------------------
# Build all subsystems
# ---------------------------------------------------------------------------

build_and_push "ai-license-mgr" "license/Dockerfile"
build_and_push "ai-train"        "train/Dockerfile"
build_and_push "ai-test"         "test/Dockerfile"
build_and_push "ai-prod"         "prod/Dockerfile"

echo ""
echo "============================================================"
echo " All images built and pushed successfully."
echo " Version: ${VERSION}"
echo "============================================================"
