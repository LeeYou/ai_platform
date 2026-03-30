#!/bin/bash
# =============================================================================
# init_host_dirs.sh
# 在宿主机上初始化 /data/ai_platform/ 目录结构
#
# 使用方法：
#   sudo bash deploy/mount_template/init_host_dirs.sh
#
# 可选参数：
#   AI_PLATFORM_ROOT=/custom/path bash init_host_dirs.sh
# =============================================================================

set -euo pipefail

ROOT="${AI_PLATFORM_ROOT:-/data/ai_platform}"

echo "[ai_platform] 初始化宿主机挂载目录: ${ROOT}"

# ---------------------------------------------------------------------------
# 能力列表（与平台首期能力一致）
# ---------------------------------------------------------------------------
CAPABILITIES=(
    face_detect
    handwriting_reco
    recapture_detect
    id_card_classify
)

ARCHS=(
    linux_x86_64
    linux_aarch64
    windows_x86_64
)

LOG_SERVICES=(train test build license prod)

# ---------------------------------------------------------------------------
# 创建基础目录
# ---------------------------------------------------------------------------
mkdir -p "${ROOT}"/{output,licenses,pipelines}

# 日志目录
for svc in "${LOG_SERVICES[@]}"; do
    mkdir -p "${ROOT}/logs/${svc}"
done

# 数据集目录
for cap in "${CAPABILITIES[@]}"; do
    mkdir -p "${ROOT}/datasets/${cap}"
done

# 模型包目录
for cap in "${CAPABILITIES[@]}"; do
    mkdir -p "${ROOT}/models/${cap}"
done

# 编译产物目录
for arch in "${ARCHS[@]}"; do
    for cap in "${CAPABILITIES[@]}"; do
        mkdir -p "${ROOT}/libs/${arch}/${cap}"
    done
done

# ---------------------------------------------------------------------------
# 复制预置 Pipeline 配置
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRESET_DIR="${SCRIPT_DIR}/pipelines"
if [ -d "${PRESET_DIR}" ]; then
    for f in "${PRESET_DIR}"/*.json; do
        [ -f "$f" ] || continue
        dest="${ROOT}/pipelines/$(basename "$f")"
        if [ ! -f "${dest}" ]; then
            cp "$f" "${dest}"
            echo "[ai_platform] 已复制预置 Pipeline: $(basename "$f")"
        fi
    done
fi

# ---------------------------------------------------------------------------
# 设置权限
# ---------------------------------------------------------------------------
# licenses 目录：仅 root 可读（防止未授权访问）
chmod 700 "${ROOT}/licenses"

# datasets 目录：只读（防止训练进程误写）
chmod -R a-w "${ROOT}/datasets" 2>/dev/null || true

# logs 目录：所有用户可写（容器以非 root 用户运行时需要）
chmod -R 777 "${ROOT}/logs"

echo "[ai_platform] 目录初始化完成！"
echo ""
echo "目录结构："
find "${ROOT}" -maxdepth 3 -type d | sort | sed 's|'"${ROOT}"'||' | sed 's|^|  /data/ai_platform|'
echo ""
echo "下一步："
echo "  1. 将训练数据集放入 ${ROOT}/datasets/<capability>/"
echo "  2. 将 license.bin 放入 ${ROOT}/licenses/<customer_id>/"
echo "  3. 运行 docker-compose up -d 启动服务"
