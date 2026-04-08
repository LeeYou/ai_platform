#!/usr/bin/env bash
# =============================================================================
# scripts/install_capability_libs.sh
# 从编译产物 tar.gz 中提取并安装能力 SO 到宿主机挂载目录
#
# 用法：
#   ./scripts/install_capability_libs.sh <artifact_tar_gz> <capability> [arch] [host_root]
#
# 示例：
#   ./scripts/install_capability_libs.sh \
#     /tmp/desktop_recapture_detect-build.tar.gz \
#     desktop_recapture_detect
# =============================================================================

set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 4 ]; then
    echo "Usage: $0 <artifact_tar_gz> <capability> [arch] [host_root]" >&2
    exit 1
fi

ARTIFACT_TAR_GZ="$1"
CAPABILITY="$2"
ARCH="${3:-linux_x86_64}"
HOST_ROOT="${4:-/data/ai_platform}"

if [ ! -f "${ARTIFACT_TAR_GZ}" ]; then
    echo "[install_capability_libs] Artifact not found: ${ARTIFACT_TAR_GZ}" >&2
    exit 1
fi

TARGET_DIR="${HOST_ROOT}/libs/${ARCH}/${CAPABILITY}/current/lib"

if [ ! -d "${TARGET_DIR}" ]; then
    echo "[install_capability_libs] Target directory does not exist: ${TARGET_DIR}" >&2
    echo "[install_capability_libs] Refusing to create current/lib automatically; please initialize host dirs first." >&2
    exit 1
fi

TMP_DIR="$(mktemp -d /tmp/ai_platform_install_libs.XXXXXX)"
chmod 700 "${TMP_DIR}"
TIMESTAMP="$(date +%F-%H%M%S)"
BACKUP_ROOT="${HOST_ROOT}/backup/${TIMESTAMP}"
BACKUP_DIR="${BACKUP_ROOT}/${CAPABILITY}"
cleanup() {
    rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

tar -xzf "${ARTIFACT_TAR_GZ}" -C "${TMP_DIR}"

find_matching_dir() {
    local pattern="$1"
    find "${TMP_DIR}" \( -type f -o -type l \) -name "${pattern}" -printf '%h\n' | sort -u | head -n 1
}

SOURCE_DIR="$(find_matching_dir "lib${CAPABILITY}.so*")"
RUNTIME_DIR="$(find_matching_dir "libai_runtime.so*")"

if [ -z "${SOURCE_DIR}" ]; then
    echo "[install_capability_libs] Could not find lib${CAPABILITY}.so* in artifact: ${ARTIFACT_TAR_GZ}" >&2
    exit 1
fi

if [ -z "${RUNTIME_DIR}" ]; then
    echo "[install_capability_libs] Could not find libai_runtime.so* in artifact: ${ARTIFACT_TAR_GZ}" >&2
    exit 1
fi

if [ "${SOURCE_DIR}" != "${RUNTIME_DIR}" ]; then
    echo "[install_capability_libs] Runtime and capability libraries were found in different directories:" >&2
    echo "  capability: ${SOURCE_DIR}" >&2
    echo "  runtime:    ${RUNTIME_DIR}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"
cp -a "${TARGET_DIR}/." "${BACKUP_DIR}/"

shopt -s nullglob
SOURCE_FILES=(
    "${SOURCE_DIR}"/libai_runtime.so*
    "${SOURCE_DIR}"/lib"${CAPABILITY}".so*
)

if [ "${#SOURCE_FILES[@]}" -eq 0 ]; then
    echo "[install_capability_libs] No installable SO files found in ${SOURCE_DIR}" >&2
    exit 1
fi

rm -f "${TARGET_DIR}"/libai_runtime.so* "${TARGET_DIR}"/lib"${CAPABILITY}".so*
cp -a "${SOURCE_DIR}"/libai_runtime.so* "${TARGET_DIR}/"
cp -a "${SOURCE_DIR}"/lib"${CAPABILITY}".so* "${TARGET_DIR}/"
shopt -u nullglob

echo "[install_capability_libs] Installed capability libs to: ${TARGET_DIR}"
echo "[install_capability_libs] Backup saved at: ${BACKUP_DIR}"
echo "[install_capability_libs] Next step: restart prod and confirm:"
echo "  [ModelLoader] Manifest OK: ${CAPABILITY} v<version> in ..."
