# CUDA 版本规范

## 版本选择

**标准 CUDA 版本：CUDA 11.8**

### 选择原因

1. **LTS（长期支持）版本**
   - CUDA 11.8 是 NVIDIA CUDA 11.x 系列的最后一个稳定版本
   - 广泛的社区支持和测试
   - 长期维护保证

2. **最佳兼容性**
   - 支持 PyTorch 2.0 - 2.4 所有版本
   - 支持 TensorFlow 2.12+
   - 支持主流深度学习框架的所有稳定版本
   - 向后兼容性好，适配大多数 GPU 型号（从 Pascal 到 Hopper 架构）

3. **生态成熟**
   - 预编译包完整：PyTorch、TensorFlow、ONNX Runtime 都有官方 CUDA 11.8 预编译版本
   - 第三方库支持好：Ultralytics、MMDetection、Detectron2 等都完美支持
   - 避免版本冲突：相比 CUDA 12.x 更成熟稳定

## 标准化要求

### 1. Docker 基础镜像

**强制要求**：所有需要 CUDA 的容器必须使用以下基础镜像：

```dockerfile
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04
```

**关键组件版本**：
- CUDA Toolkit: 11.8.0
- cuDNN: 8.x
- 操作系统: Ubuntu 22.04 LTS

### 2. PyTorch 安装

**标准安装方式**：

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

**版本约束**（requirements.txt）：

```txt
# PyTorch 2.x for CUDA 11.8
torch>=2.0.0,<2.5.0
torchvision>=0.15.0,<0.20.0
```

**说明**：
- 使用 PyTorch 2.0-2.4 系列（CUDA 11.8 完全支持）
- 避免使用 PyTorch 2.5+ （可能需要 CUDA 12.x）

### 3. 其他深度学习框架

#### ONNX Runtime

```txt
onnxruntime-gpu==1.18.1  # 官方支持 CUDA 11.8
```

#### Ultralytics (YOLOv8)

```txt
ultralytics==8.2.0  # 测试验证兼容 CUDA 11.8 + PyTorch 2.x
```

### 4. 构建系统要求

对于需要编译 CUDA 扩展的项目：

```cmake
# CMakeLists.txt
set(CUDA_TOOLKIT_ROOT_DIR /usr/local/cuda-11.8)
find_package(CUDA 11.8 REQUIRED)
```

## 镜像兼容性矩阵

| 镜像名称 | CUDA 版本 | 用途 | 状态 |
|---------|----------|------|------|
| `train` | 11.8.0 | 模型训练 | ✅ 标准 |
| `test` | N/A (CPU) | 模型测试 | ✅ 不需要 CUDA |
| `prod` | N/A (CPU) | 生产推理（使用 ONNX Runtime CPU） | ✅ 不需要 CUDA |
| `build` | N/A (CPU) | C++ 编译构建 | ✅ 不需要 CUDA |

**说明**：
- 只有 `train` 镜像需要 CUDA（用于 GPU 训练）
- 其他镜像使用 CPU 版本，降低资源消耗和部署复杂度
- 生产环境推理使用 ONNX Runtime CPU 版本，无需 GPU

## 依赖库版本兼容表

### 已验证的兼容组合

```txt
# 核心深度学习栈（CUDA 11.8）
cuda==11.8.0
cudnn==8.x
python==3.10
torch==2.4.1+cu118
torchvision==0.19.1+cu118
onnx==1.16.0
onnxruntime-gpu==1.18.1

# 计算机视觉
opencv-python-headless==4.10.0
Pillow==10.0.0

# YOLO 系列
ultralytics==8.2.0
onnxslim==0.1.0

# 科学计算
numpy>=1.24.0,<2.0
scikit-learn>=1.4.0
```

## 迁移指南

### 从其他 CUDA 版本迁移到 11.8

#### 从 CUDA 12.x 降级

1. **更新 Dockerfile 基础镜像**：
   ```dockerfile
   # 修改前
   FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04

   # 修改后
   FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04
   ```

2. **更新 PyTorch 安装**：
   ```bash
   # 修改前
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

   # 修改后
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
   ```

3. **验证兼容性**：
   ```python
   import torch
   print(f"PyTorch: {torch.__version__}")
   print(f"CUDA available: {torch.cuda.is_available()}")
   print(f"CUDA version: {torch.version.cuda}")
   ```

### 验证检查清单

构建新镜像后，执行以下检查：

```bash
# 1. 检查 CUDA 版本
nvidia-smi
nvcc --version  # 应输出 11.8

# 2. 检查 PyTorch CUDA
python3 -c "import torch; print(f'PyTorch {torch.__version__}, CUDA {torch.version.cuda}, Available: {torch.cuda.is_available()}')"

# 3. 检查 cuDNN
python3 -c "import torch; print(f'cuDNN version: {torch.backends.cudnn.version()}')"

# 4. 验证 GPU 计算
python3 -c "import torch; x = torch.rand(5, 3).cuda(); print('GPU test passed')"
```

## 常见问题 (FAQ)

### Q1: 为什么选择 CUDA 11.8 而不是最新的 CUDA 12.x？

**A**:
- CUDA 12.x 是较新版本，但生态还不够成熟
- 部分依赖库（如 ONNX Runtime、Ultralytics）对 CUDA 12.x 支持不完整
- CUDA 11.8 兼容性最佳，避免版本冲突
- PyTorch 2.0-2.4 官方推荐使用 CUDA 11.8

### Q2: 如果必须使用 CUDA 12.x 怎么办？

**A**:
- 仅在特定项目需要时使用，不作为默认标准
- 确保所有依赖库都有 CUDA 12.x 版本
- 充分测试兼容性
- 在 Dockerfile 中通过 ARG 参数显式指定

### Q3: 如何处理 "CUDA version mismatch" 错误？

**A**:
```bash
# 检查运行时 CUDA 版本
nvidia-smi  # 查看驱动支持的 CUDA 版本

# 检查 PyTorch 编译的 CUDA 版本
python3 -c "import torch; print(torch.version.cuda)"

# 确保两者兼容：
# - 驱动版本 >= 编译版本
# - 例如：驱动支持 12.2，可以运行 CUDA 11.8 编译的程序
```

### Q4: 训练镜像很大，如何优化？

**A**:
- 使用多阶段构建分离编译和运行时依赖
- 及时清理 apt/pip 缓存
- 仅安装必要的 CUDA 组件
- 参考 `DOCKER_BUILD_OPTIMIZATION.md`

## 代码审查要求

提交涉及 CUDA 依赖的代码时，必须检查：

1. ✅ Dockerfile 使用标准 CUDA 11.8 基础镜像
2. ✅ PyTorch 安装使用 `cu118` 索引
3. ✅ requirements.txt 指定兼容的版本范围
4. ✅ 代码注释说明 CUDA 版本要求
5. ✅ 更新相关文档（如有必要）

## 相关文档

- [Docker 构建优化指南](../DOCKER_BUILD_OPTIMIZATION.md)
- [训练子系统设计](./design/train_service.md)
- [性能优化指南](./performance_optimization_guide.md)

## 版本历史

| 版本 | 日期 | 变更说明 |
|-----|------|---------|
| 1.0 | 2026-03-31 | 初始版本，确定 CUDA 11.8 为标准版本 |

---

**更新时间**：2026-03-31
**维护者**：AI Platform Team
