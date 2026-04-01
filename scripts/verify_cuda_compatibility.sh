#!/bin/bash
# =============================================================================
# CUDA 兼容性验证脚本
#
# 用途：验证训练镜像中 CUDA 环境是否正确配置
# 使用：docker exec -it <train-container> bash /app/scripts/verify_cuda_compatibility.sh
# =============================================================================

set -e

echo "========================================="
echo "CUDA 兼容性验证检查"
echo "标准版本：CUDA 11.8.0"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 错误计数
ERRORS=0

# 检查函数
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((ERRORS++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo "1. 检查 CUDA Toolkit 版本..."
if command -v nvcc &> /dev/null; then
    NVCC_VERSION=$(nvcc --version | grep "release" | sed -n 's/.*release \([0-9.]*\).*/\1/p')
    if [ "$NVCC_VERSION" == "11.8" ]; then
        check_pass "CUDA Toolkit 版本: $NVCC_VERSION (正确)"
    else
        check_fail "CUDA Toolkit 版本: $NVCC_VERSION (期望: 11.8)"
    fi
else
    check_fail "nvcc 命令不可用"
fi
echo ""

echo "2. 检查 NVIDIA 驱动..."
if command -v nvidia-smi &> /dev/null; then
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
    CUDA_DRIVER=$(nvidia-smi | grep "CUDA Version" | sed -n 's/.*CUDA Version: \([0-9.]*\).*/\1/p')
    check_pass "NVIDIA 驱动版本: $DRIVER_VERSION"
    check_pass "驱动支持的 CUDA 版本: $CUDA_DRIVER"

    # 检查驱动是否支持 CUDA 11.8
    MAJOR_VERSION=$(echo $CUDA_DRIVER | cut -d. -f1)
    if [ "$MAJOR_VERSION" -ge "11" ]; then
        check_pass "驱动兼容 CUDA 11.8"
    else
        check_fail "驱动版本过低，不支持 CUDA 11.8"
    fi
else
    check_warn "nvidia-smi 不可用（可能在非 GPU 环境）"
fi
echo ""

echo "3. 检查 Python 环境..."
PYTHON_VERSION=$(python3 --version | sed -n 's/Python \([0-9.]*\).*/\1/p')
if [[ "$PYTHON_VERSION" == 3.10* ]]; then
    check_pass "Python 版本: $PYTHON_VERSION (推荐)"
elif [[ "$PYTHON_VERSION" == 3.* ]]; then
    check_warn "Python 版本: $PYTHON_VERSION (可用，但推荐 3.10)"
else
    check_fail "Python 版本: $PYTHON_VERSION (不兼容)"
fi
echo ""

echo "4. 检查 PyTorch 安装..."
if python3 -c "import torch" 2>/dev/null; then
    TORCH_VERSION=$(python3 -c "import torch; print(torch.__version__)")
    TORCH_CUDA=$(python3 -c "import torch; print(torch.version.cuda)")
    CUDA_AVAILABLE=$(python3 -c "import torch; print(torch.cuda.is_available())")

    check_pass "PyTorch 版本: $TORCH_VERSION"

    if [ "$TORCH_CUDA" == "11.8" ]; then
        check_pass "PyTorch CUDA 版本: $TORCH_CUDA (正确)"
    else
        check_fail "PyTorch CUDA 版本: $TORCH_CUDA (期望: 11.8)"
    fi

    if [ "$CUDA_AVAILABLE" == "True" ]; then
        check_pass "CUDA 可用性: True"

        # 检查 GPU 数量
        GPU_COUNT=$(python3 -c "import torch; print(torch.cuda.device_count())")
        check_pass "检测到 $GPU_COUNT 个 GPU"

        # 获取 GPU 名称
        for i in $(seq 0 $((GPU_COUNT-1))); do
            GPU_NAME=$(python3 -c "import torch; print(torch.cuda.get_device_name($i))")
            check_pass "GPU $i: $GPU_NAME"
        done
    else
        check_warn "CUDA 可用性: False（可能在 CPU 模式运行）"
    fi
else
    check_fail "PyTorch 未安装或无法导入"
fi
echo ""

echo "5. 检查 cuDNN..."
if python3 -c "import torch; torch.backends.cudnn.version()" 2>/dev/null; then
    CUDNN_VERSION=$(python3 -c "import torch; print(torch.backends.cudnn.version())")
    CUDNN_ENABLED=$(python3 -c "import torch; print(torch.backends.cudnn.enabled)")

    check_pass "cuDNN 版本: $CUDNN_VERSION"
    check_pass "cuDNN 启用: $CUDNN_ENABLED"
else
    check_fail "cuDNN 不可用"
fi
echo ""

echo "6. 检查关键依赖库..."

# 检查 OpenCV
if python3 -c "import cv2" 2>/dev/null; then
    CV2_VERSION=$(python3 -c "import cv2; print(cv2.__version__)")
    check_pass "OpenCV 版本: $CV2_VERSION"
else
    check_fail "OpenCV 未安装"
fi

# 检查 Pillow
if python3 -c "from PIL import Image" 2>/dev/null; then
    PIL_VERSION=$(python3 -c "from PIL import Image; print(Image.__version__)" 2>/dev/null || echo "未知")
    check_pass "Pillow 已安装"
else
    check_fail "Pillow 未安装"
fi

# 检查 ONNX
if python3 -c "import onnx" 2>/dev/null; then
    ONNX_VERSION=$(python3 -c "import onnx; print(onnx.__version__)")
    check_pass "ONNX 版本: $ONNX_VERSION"
else
    check_warn "ONNX 未安装（某些能力可能需要）"
fi

# 检查 ONNXRuntime
if python3 -c "import onnxruntime" 2>/dev/null; then
    ORT_VERSION=$(python3 -c "import onnxruntime; print(onnxruntime.__version__)")
    check_pass "ONNXRuntime 版本: $ORT_VERSION"
else
    check_warn "ONNXRuntime 未安装（某些能力可能需要）"
fi

# 检查 Ultralytics (如果安装了)
if python3 -c "import ultralytics" 2>/dev/null; then
    UL_VERSION=$(python3 -c "import ultralytics; print(ultralytics.__version__)")
    if [ "$UL_VERSION" == "8.2.0" ]; then
        check_pass "Ultralytics 版本: $UL_VERSION (正确)"
    else
        check_warn "Ultralytics 版本: $UL_VERSION (推荐: 8.2.0)"
    fi
else
    check_warn "Ultralytics 未安装（face_detect 需要）"
fi

echo ""

echo "7. GPU 计算测试..."
if [ "$CUDA_AVAILABLE" == "True" ]; then
    if python3 -c "import torch; x = torch.rand(100, 100).cuda(); y = x @ x; print('GPU 计算测试通过')" 2>/dev/null; then
        check_pass "GPU 矩阵运算测试通过"
    else
        check_fail "GPU 计算测试失败"
    fi
else
    check_warn "跳过 GPU 测试（CUDA 不可用）"
fi
echo ""

echo "========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}验证通过！所有检查项正常。${NC}"
    echo "========================================="
    exit 0
else
    echo -e "${RED}验证失败！发现 $ERRORS 个错误。${NC}"
    echo "请检查上述错误项并参考文档："
    echo "  docs/cuda_version_standard.md"
    echo "========================================="
    exit 1
fi
