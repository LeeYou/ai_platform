#!/usr/bin/env bash
# =============================================================================
# scripts/package_delivery.sh
# 打包生产交付物（Docker 镜像 tar + SDK + 文档）
#
# 用法：
#   ./scripts/package_delivery.sh [VERSION] [OUTPUT_DIR]
#
# 支持多架构交付：linux_x86_64、linux_aarch64、windows_x86_64
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
# 1. Docker image tarballs (multi-arch)
# ---------------------------------------------------------------------------
echo ""
echo "---- Saving Docker images ----"

declare -A IMAGE_ARCH_MAP=(
    ["ai-prod"]="linux-x86_64"
)

for image in ai-prod; do
    tag="agilestar/${image}:${VERSION}"
    arch="${IMAGE_ARCH_MAP[$image]}"
    outfile="${OUTPUT_DIR}/docker/agilestar-${image}-${arch}-v${VERSION}.tar.gz"
    if docker inspect "${tag}" > /dev/null 2>&1; then
        docker save "${tag}" | gzip > "${outfile}"
        echo "  Saved: ${outfile}"
    else
        echo "  WARNING: image ${tag} not found, skipping"
    fi
done

# ---------------------------------------------------------------------------
# 2. SDK headers (multi-arch)
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying SDK headers ----"

for arch in linux_x86_64 linux_aarch64 windows_x86_64; do
    SDK_DIR="${OUTPUT_DIR}/sdk_${arch}/include/agilestar"
    mkdir -p "${SDK_DIR}"
    cp "${REPO_ROOT}/cpp/sdk/"*.h "${SDK_DIR}/" 2>/dev/null || true
    echo "  Copied SDK headers to ${SDK_DIR}"
done

# ---------------------------------------------------------------------------
# 3. JNI headers (for Java/Android integration)
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying JNI headers ----"
JNI_DIR="${OUTPUT_DIR}/sdk_jni/include/agilestar/jni"
mkdir -p "${JNI_DIR}"
cp "${REPO_ROOT}/cpp/jni/cn_agilestar_ai_AiCapability.h" "${JNI_DIR}/" 2>/dev/null || true
echo "  Copied JNI headers to ${JNI_DIR}"

# ---------------------------------------------------------------------------
# 4. Documentation
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying documentation ----"
cp "${REPO_ROOT}/docs/"*.md "${OUTPUT_DIR}/docs/" 2>/dev/null || true
# Include design docs subdirectory
if [ -d "${REPO_ROOT}/docs/design" ]; then
    mkdir -p "${OUTPUT_DIR}/docs/design"
    cp "${REPO_ROOT}/docs/design/"*.md "${OUTPUT_DIR}/docs/design/" 2>/dev/null || true
fi
cp "${REPO_ROOT}/README.md" "${OUTPUT_DIR}/docs/" 2>/dev/null || true
cp "${REPO_ROOT}/CHANGELOG.md" "${OUTPUT_DIR}/docs/" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 5. Mount template
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying mount template ----"
cp -r "${REPO_ROOT}/deploy/mount_template/." "${OUTPUT_DIR}/mount_template/"

# ---------------------------------------------------------------------------
# 6. License tool
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying license tool ----"
if [ -f "${REPO_ROOT}/license/tools/license_tool" ]; then
    cp "${REPO_ROOT}/license/tools/license_tool" "${OUTPUT_DIR}/tools/"
elif [ -d "${REPO_ROOT}/license/tools" ]; then
    cp -r "${REPO_ROOT}/license/tools/." "${OUTPUT_DIR}/tools/"
fi

# ---------------------------------------------------------------------------
# 6.1 Deployment helper scripts
# ---------------------------------------------------------------------------
echo ""
echo "---- Copying deployment helper scripts ----"
cp "${REPO_ROOT}/scripts/install_capability_libs.sh" "${OUTPUT_DIR}/tools/" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 7. Create delivery manifest
# ---------------------------------------------------------------------------
echo ""
echo "---- Writing delivery manifest ----"
cat > "${OUTPUT_DIR}/DELIVERY_MANIFEST.txt" << EOF
AI 能力平台 — 生产交付清单
北京爱知之星科技股份有限公司 (Agile Star)
版本: ${VERSION}
打包时间: $(date -u '+%Y-%m-%dT%H:%M:%SZ')

交付内容:
  docker/                — Docker 镜像压缩包
  sdk_linux_x86_64/      — C/C++ SDK 头文件（Linux x86_64）
  sdk_linux_aarch64/     — C/C++ SDK 头文件（Linux aarch64）
  sdk_windows_x86_64/    — C/C++ SDK 头文件（Windows x86_64）
  sdk_jni/               — JNI 头文件（Java/Android 集成）
  docs/                  — API文档、部署手册、运维手册
  tools/                 — 授权管理工具 / SO 安装辅助脚本
  mount_template/        — 宿主机挂载目录模板

部署说明：
  1. 导入 Docker 镜像：
        docker load < docker/agilestar-ai-prod-linux-x86_64-v${VERSION}.tar.gz
  2. 按 mount_template/ 创建宿主机目录结构：
       bash mount_template/init_host_dirs.sh
  3. 放置 pubkey.pem + license.bin 到 /data/ai_platform/licenses/
  4. 放置模型包到 /data/ai_platform/models/<capability>/current/
  5. 如需替换客户专属 SO，优先使用：
       bash tools/install_capability_libs.sh <artifact.tar.gz> <capability>
  6. 启动服务：
        cd deploy && docker compose -f docker-compose.prod.yml up -d

  详见 docs/deployment_manual.md
EOF

echo "  Written: ${OUTPUT_DIR}/DELIVERY_MANIFEST.txt"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Delivery package created at: ${OUTPUT_DIR}"
echo " Version: ${VERSION}"
echo ""
echo " Contents:"
echo "   docker/              - Docker image tarballs"
echo "   sdk_linux_x86_64/    - SDK headers (Linux x86_64)"
echo "   sdk_linux_aarch64/   - SDK headers (Linux aarch64)"
echo "   sdk_windows_x86_64/  - SDK headers (Windows x86_64)"
echo "   sdk_jni/             - JNI headers (Java/Android)"
echo "   docs/                - Documentation"
echo "   tools/               - License tools"
echo "   mount_template/      - Host directory template"
echo "============================================================"
