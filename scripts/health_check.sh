#!/bin/bash
# =============================================================================
# health_check.sh
# 一键检查 AI 能力平台所有服务的健康状态
#
# 使用方法：
#   bash scripts/health_check.sh              # 检查所有服务
#   bash scripts/health_check.sh dev          # 仅检查开发环境服务
#   bash scripts/health_check.sh prod         # 仅检查生产环境服务
#
# 环境变量（可选）：
#   DEV_HOST=192.168.1.100  bash scripts/health_check.sh   # 指定开发机地址
#   PROD_HOST=10.0.0.50     bash scripts/health_check.sh   # 指定生产机地址
#   TIMEOUT=10              bash scripts/health_check.sh   # 指定超时秒数
# =============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
DEV_HOST="${DEV_HOST:-localhost}"
PROD_HOST="${PROD_HOST:-localhost}"
TIMEOUT="${TIMEOUT:-5}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 计数器
PASS=0
FAIL=0
SKIP=0

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
print_header() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  AI 能力平台 — 服务健康检查${NC}"
    echo -e "${CYAN}  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

check_service() {
    local name="$1"
    local url="$2"
    local expected_field="${3:-status}"

    printf "  %-20s %s ... " "$name" "$url"

    local response
    local http_code
    http_code=$(curl -sf -o /tmp/health_check_response.json -w "%{http_code}" \
        --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" "$url" 2>/dev/null)

    if [ "$http_code" = "200" ]; then
        response=$(cat /tmp/health_check_response.json 2>/dev/null)
        local status_val
        status_val=$(echo "$response" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('$expected_field', 'unknown'))
except:
    print('parse_error')
" 2>/dev/null)

        if [ "$status_val" = "ok" ] || [ "$status_val" = "healthy" ]; then
            echo -e "${GREEN}✅ OK${NC} (${status_val})"
            PASS=$((PASS + 1))
        elif [ "$status_val" = "degraded" ]; then
            echo -e "${YELLOW}⚠️  DEGRADED${NC}"
            PASS=$((PASS + 1))
        else
            echo -e "${YELLOW}⚠️  UNEXPECTED${NC} (${status_val})"
            PASS=$((PASS + 1))
        fi
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP ${http_code:-timeout})"
        FAIL=$((FAIL + 1))
    fi
}

check_docker_container() {
    local container_name="$1"
    printf "  %-20s docker inspect ... " "$container_name"

    if ! command -v docker &>/dev/null; then
        echo -e "${YELLOW}⏭️  SKIP${NC} (docker not found)"
        SKIP=$((SKIP + 1))
        return
    fi

    local state
    state=$(docker inspect --format='{{.State.Status}}' "$container_name" 2>/dev/null)

    if [ "$state" = "running" ]; then
        local health
        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container_name" 2>/dev/null)
        if [ "$health" = "healthy" ]; then
            echo -e "${GREEN}✅ RUNNING (healthy)${NC}"
            PASS=$((PASS + 1))
        elif [ "$health" = "no-healthcheck" ]; then
            echo -e "${GREEN}✅ RUNNING${NC}"
            PASS=$((PASS + 1))
        else
            echo -e "${YELLOW}⚠️  RUNNING (${health})${NC}"
            PASS=$((PASS + 1))
        fi
    elif [ -z "$state" ]; then
        echo -e "${RED}❌ NOT FOUND${NC}"
        FAIL=$((FAIL + 1))
    else
        echo -e "${RED}❌ ${state}${NC}"
        FAIL=$((FAIL + 1))
    fi
}

check_gpu() {
    printf "  %-20s nvidia-smi ... " "GPU"
    if command -v nvidia-smi &>/dev/null; then
        local gpu_info
        gpu_info=$(nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu \
            --format=csv,noheader,nounits 2>/dev/null | head -1)
        if [ -n "$gpu_info" ]; then
            echo -e "${GREEN}✅ OK${NC} (${gpu_info})"
            PASS=$((PASS + 1))
        else
            echo -e "${RED}❌ FAIL${NC} (nvidia-smi error)"
            FAIL=$((FAIL + 1))
        fi
    else
        echo -e "${YELLOW}⏭️  SKIP${NC} (nvidia-smi not found)"
        SKIP=$((SKIP + 1))
    fi
}

check_disk() {
    local path="${1:-/data/ai_platform}"
    printf "  %-20s df %s ... " "Disk" "$path"
    if [ -d "$path" ]; then
        local usage
        usage=$(df -h "$path" 2>/dev/null | tail -1 | awk '{print $5}')
        local avail
        avail=$(df -h "$path" 2>/dev/null | tail -1 | awk '{print $4}')
        local usage_num
        usage_num=$(echo "$usage" | tr -d '%')
        if [ "$usage_num" -lt 80 ]; then
            echo -e "${GREEN}✅ OK${NC} (used: ${usage}, avail: ${avail})"
            PASS=$((PASS + 1))
        elif [ "$usage_num" -lt 95 ]; then
            echo -e "${YELLOW}⚠️  WARNING${NC} (used: ${usage}, avail: ${avail})"
            PASS=$((PASS + 1))
        else
            echo -e "${RED}❌ CRITICAL${NC} (used: ${usage}, avail: ${avail})"
            FAIL=$((FAIL + 1))
        fi
    else
        echo -e "${YELLOW}⏭️  SKIP${NC} (path not found)"
        SKIP=$((SKIP + 1))
    fi
}

print_summary() {
    local total=$((PASS + FAIL + SKIP))
    echo ""
    echo -e "${CYAN}────────────────────────────────────────────────────────────${NC}"
    echo -e "  总计: ${total} 项检查"
    echo -e "  ${GREEN}✅ 通过: ${PASS}${NC}  ${RED}❌ 失败: ${FAIL}${NC}  ${YELLOW}⏭️  跳过: ${SKIP}${NC}"
    echo -e "${CYAN}────────────────────────────────────────────────────────────${NC}"
    echo ""

    if [ "$FAIL" -gt 0 ]; then
        echo -e "${RED}存在异常服务，请检查上述失败项！${NC}"
        return 1
    else
        echo -e "${GREEN}所有服务运行正常。${NC}"
        return 0
    fi
}

# ---------------------------------------------------------------------------
# 检查逻辑
# ---------------------------------------------------------------------------
check_dev_services() {
    echo -e "${CYAN}【开发环境服务】 Host: ${DEV_HOST}${NC}"
    echo ""

    echo "  容器状态："
    check_docker_container "ai-license-mgr"
    check_docker_container "ai-train"
    check_docker_container "ai-test"
    check_docker_container "ai-builder"
    check_docker_container "ai-redis"
    echo ""

    echo "  HTTP 健康检查："
    check_service "License (8003)" "http://${DEV_HOST}:8003/health" "status"
    check_service "Train   (8001)" "http://${DEV_HOST}:8001/health" "status"
    check_service "Test    (8002)" "http://${DEV_HOST}:8002/health" "status"
    check_service "Build   (8004)" "http://${DEV_HOST}:8004/health" "status"
    echo ""
}

check_prod_services() {
    echo -e "${CYAN}【生产环境服务】 Host: ${PROD_HOST}${NC}"
    echo ""

    echo "  容器状态："
    check_docker_container "ai-prod"
    echo ""

    echo "  HTTP 健康检查："
    check_service "Prod    (8080)" "http://${PROD_HOST}:8080/api/v1/health" "status"
    echo ""
}

check_system() {
    echo -e "${CYAN}【系统资源】${NC}"
    echo ""
    check_gpu
    check_disk "/data/ai_platform"
    echo ""
}

# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------
main() {
    local mode="${1:-all}"

    print_header

    case "$mode" in
        dev)
            check_dev_services
            check_system
            ;;
        prod)
            check_prod_services
            check_system
            ;;
        all|*)
            check_dev_services
            check_prod_services
            check_system
            ;;
    esac

    print_summary
}

main "$@"
