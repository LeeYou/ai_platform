#!/usr/bin/env bash
# =============================================================================
# scripts/package_delivery.sh
# 打包生产交付物（Docker 镜像 tar + SDK + 文档）
#
# 用法：
#   ./scripts/package_delivery.sh [VERSION] [OUTPUT_DIR]
#
# Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
# =============================================================================

set -euo pipefail

VERSION="${1:-1.0.0}"
OUTPUT_DIR="${2:-/tmp/delivery_${VERSION}}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "============================================================"
echo " AI Platform Delivery Packager"
echo " Version   : ${VERSION}"
echo " Output dir: ${OUTPUT_DIR}"
echo "============================================================"

mkdir -p \
    "${OUTPUT_DIR}/docker" \
    "${OUTPUT_DIR}/docs" \
    "${OUTPUT_DIR}/tools" \
    "${OUTPUT_DIR}/mount_template"

# ---------------------------------------------------------------------------
# 1. Docker image tarballs
# ---------------------------------------------------------------------------
echo ""
echo "---- Saving Docker images ----"

for image in ai-prod; do
    tag="agilestar/${image}:${VERSION}"
    outfile="${OUTPUT_DIR}/docker/agilestar-${image}-linux-x86_64-v${VERSION}.tar.gz"
    if docker inspect "${tag}" > /dev/null 2>&1; then
        docker save "${tag}" | gzip > "${outfile}"
        echo "  Saved: ${outfile}"
    else
        echo "  WARNING: image ${tag} not found, skipping"
    fi
done

# ---------------------------------------------------------------------------
# 2. SDK headers
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying SDK headers ----"
SDK_DIR="${OUTPUT_DIR}/sdk_linux_x86_64/include/agilestar"
mkdir -p "${SDK_DIR}"
cp "${REPO_ROOT}/cpp/sdk/"*.h "${SDK_DIR}/" 2>/dev/null || true
echo "  Copied SDK headers to ${SDK_DIR}"

# ---------------------------------------------------------------------------
# 3. Documentation
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying documentation ----"
cp "${REPO_ROOT}/docs/"* "${OUTPUT_DIR}/docs/" 2>/dev/null || true
cp "${REPO_ROOT}/README.md" "${OUTPUT_DIR}/docs/" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 4. Mount template
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying mount template ----"
cp -r "${REPO_ROOT}/deploy/mount_template/." "${OUTPUT_DIR}/mount_template/"

# ---------------------------------------------------------------------------
# 5. License tool
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying license tool ----"
if [ -f "${REPO_ROOT}/license/tools/license_tool" ]; then
    cp "${REPO_ROOT}/license/tools/license_tool" "${OUTPUT_DIR}/tools/"
elif [ -d "${REPO_ROOT}/license/tools" ]; then
    cp -r "${REPO_ROOT}/license/tools/." "${OUTPUT_DIR}/tools/"
fi

# ---------------------------------------------------------------------------
# 6. Create delivery manifest
# ---------------------------------------------------------------------------
echo ""
echo "---- Writing delivery manifest ----"
cat > "${OUTPUT_DIR}/DELIVERY_MANIFEST.txt" << EOF
AI 能力平台 — 生产交付清单
北京爱知之星科技股份有限公司 (Agile Star)
版本: ${VERSION}
打包时间: $(date -u '+%Y-%m-%dT%H:%M:%SZ')

交付内容:
  docker/        — Docker 镜像压缩包
  sdk/           — C/C++ SDK 头文件
  docs/          — API文档、部署手册
  tools/         — 授权查询工具
  mount_template/— 宿主机挂载目录模板

部署说明：
  1. 导入 Docker 镜像：
       docker load < docker/agilestar-ai-prod-linux-x86_64-v${VERSION}.tar.gz
  2. 按 mount_template/ 创建宿主机目录结构
  3. 放置 license.bin 到 /data/ai_platform/licenses/
  4. 放置模型包到 /data/ai_platform/models/<capability>/current/
  5. 启动服务：
       docker run -d --name ai-prod \\
         -p 8080:8080 \\
         -v /data/ai_platform/models:/mnt/ai_platform/models:ro \\
         -v /data/ai_platform/licenses:/mnt/ai_platform/licenses:ro \\
         agilestar/ai-prod:${VERSION}

详见 docs/部署手册.md
EOF

echo "  Written: ${OUTPUT_DIR}/DELIVERY_MANIFEST.txt"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Delivery package created at: ${OUTPUT_DIR}"
echo " Version: ${VERSION}"
echo "============================================================"
