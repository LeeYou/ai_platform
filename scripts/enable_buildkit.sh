#!/bin/bash
# =============================================================================
# scripts/enable_buildkit.sh
# 启用 Docker BuildKit 构建系统
#
# BuildKit 提供：
#   1. 并行构建层
#   2. 缓存挂载 (--mount=type=cache)
#   3. 更好的构建输出
#   4. 构建密钥管理
#
# 使用方法：
#   source scripts/enable_buildkit.sh
# =============================================================================

# 启用 BuildKit
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# 添加到 shell 配置文件（如果还没有）
SHELL_RC=""
if [ -f ~/.bashrc ]; then
    SHELL_RC=~/.bashrc
elif [ -f ~/.zshrc ]; then
    SHELL_RC=~/.zshrc
fi

if [ -n "$SHELL_RC" ]; then
    if ! grep -q "DOCKER_BUILDKIT=1" "$SHELL_RC"; then
        echo "" >> "$SHELL_RC"
        echo "# Docker BuildKit" >> "$SHELL_RC"
        echo "export DOCKER_BUILDKIT=1" >> "$SHELL_RC"
        echo "export COMPOSE_DOCKER_CLI_BUILD=1" >> "$SHELL_RC"
        echo "✅ BuildKit 配置已添加到 $SHELL_RC"
        echo "   请运行: source $SHELL_RC"
    else
        echo "ℹ️  BuildKit 配置已存在于 $SHELL_RC"
    fi
fi

echo ""
echo "当前会话 BuildKit 状态："
echo "  DOCKER_BUILDKIT=$DOCKER_BUILDKIT"
echo "  COMPOSE_DOCKER_CLI_BUILD=$COMPOSE_DOCKER_CLI_BUILD"
echo ""
echo "使用优化后的 Dockerfile 构建："
echo "  docker compose build train"
echo "  或"
echo "  docker build -t agilestar/ai-train:latest -f train/Dockerfile.optimized ."
