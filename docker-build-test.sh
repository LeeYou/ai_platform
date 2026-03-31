#!/bin/bash
# Docker 构建验证脚本
# Docker Build Verification Script
#
# 此脚本用于验证 Docker 构建优化是否正常工作
# This script verifies that Docker build optimizations are working correctly

set -e

echo "======================================================================"
echo "Docker 构建优化验证"
echo "Docker Build Optimization Verification"
echo "======================================================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 测试函数
test_dockerfile() {
    local dockerfile=$1
    local image_name=$2

    echo -e "${YELLOW}测试 $dockerfile...${NC}"
    echo -e "${YELLOW}Testing $dockerfile...${NC}"
    echo ""

    # 第一次构建
    echo "第一次构建 (First build)..."
    docker build -f "$dockerfile" -t "$image_name:test1" . 2>&1 | tee /tmp/docker_build_1.log

    # 检查是否使用了镜像源
    echo ""
    echo "检查镜像源配置 (Checking mirror sources)..."
    if grep -q "pypi.tuna.tsinghua.edu.cn" /tmp/docker_build_1.log; then
        echo -e "${GREEN}✓ 检测到清华 pip 镜像源${NC}"
    fi

    if grep -q "registry.npmmirror.com" /tmp/docker_build_1.log; then
        echo -e "${GREEN}✓ 检测到淘宝 npm 镜像源${NC}"
    fi

    # 修改一个后端文件（模拟代码改动）
    echo ""
    echo "模拟源代码改动 (Simulating source code change)..."
    touch .docker_test_marker

    # 第二次构建
    echo "第二次构建 (Second build - should use cache)..."
    docker build -f "$dockerfile" -t "$image_name:test2" . 2>&1 | tee /tmp/docker_build_2.log

    # 检查缓存是否命中
    echo ""
    echo "检查缓存命中情况 (Checking cache hits)..."
    if grep -q "Using cache" /tmp/docker_build_2.log; then
        echo -e "${GREEN}✓ 层缓存正常工作 (Layer cache is working)${NC}"
        cache_hits=$(grep -c "Using cache" /tmp/docker_build_2.log)
        echo -e "${GREEN}  缓存命中次数: $cache_hits${NC}"
    else
        echo -e "${RED}✗ 警告：未检测到缓存命中${NC}"
        echo -e "${RED}  Warning: No cache hits detected${NC}"
    fi

    # 清理测试镜像
    echo ""
    echo "清理测试镜像 (Cleaning up test images)..."
    docker rmi "$image_name:test1" "$image_name:test2" 2>/dev/null || true
    rm -f .docker_test_marker

    echo ""
    echo -e "${GREEN}$dockerfile 验证完成${NC}"
    echo "======================================================================"
    echo ""
}

# 主测试流程
echo "请选择要测试的 Dockerfile:"
echo "Please select which Dockerfile to test:"
echo ""
echo "1) train/Dockerfile (训练镜像)"
echo "2) test/Dockerfile (测试镜像)"
echo "3) prod/Dockerfile (生产镜像)"
echo "4) license/backend/Dockerfile (授权服务镜像)"
echo "5) 全部测试 (Test all)"
echo ""
read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        test_dockerfile "train/Dockerfile" "agilestar/ai-train"
        ;;
    2)
        test_dockerfile "test/Dockerfile" "agilestar/ai-test"
        ;;
    3)
        test_dockerfile "prod/Dockerfile" "agilestar/ai-prod"
        ;;
    4)
        test_dockerfile "license/backend/Dockerfile" "agilestar/ai-license"
        ;;
    5)
        test_dockerfile "train/Dockerfile" "agilestar/ai-train"
        test_dockerfile "test/Dockerfile" "agilestar/ai-test"
        test_dockerfile "prod/Dockerfile" "agilestar/ai-prod"
        test_dockerfile "license/backend/Dockerfile" "agilestar/ai-license"
        ;;
    *)
        echo -e "${RED}无效选项${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}======================================================================"
echo "验证完成！"
echo "Verification complete!"
echo "======================================================================${NC}"
echo ""
echo "关键指标说明 (Key Metrics):"
echo "- ✓ 镜像源: 如果看到清华/淘宝源，说明镜像源配置成功"
echo "- ✓ 缓存命中: 如果第二次构建有大量 'Using cache'，说明层缓存优化成功"
echo ""
echo "预期性能提升 (Expected Performance Improvements):"
echo "- 缓存命中时: 构建时间减少 90%+ (5-10秒 vs 2-5分钟)"
echo "- 首次构建: 下载速度提升 50-100倍 (pip) 和 20-30倍 (npm)"
echo ""
