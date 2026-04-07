# 编译子系统设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-27**

---

## 1. 概述

编译子系统负责将 C++ 推理代码编译为各目标平台的 SO/DLL 二进制产物，并通过 Web 界面管理编译任务和产物版本。每个 AI 能力对应一个独立的 CMake 子工程（插件），共享公共 SDK 头文件和 Runtime 库。

---

## 2. 编译容器设计

### 2.1 Linux x86_64 编译容器

| 属性 | 值 |
|------|-----|
| 镜像名 | `agilestar/ai-builder-linux-x86:latest`（CPU/ORT） / `agilestar/ai-builder-linux-x86-gpu:latest`（CUDA devel） |
| 基础镜像 | CPU Builder：`ubuntu:22.04` / GPU Builder：`nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04` |
| 编译器 | GCC 12 / G++ 12 |
| CMake 版本 | ≥3.26 |
| 推理框架 | ONNXRuntime 1.18.1（CPU/GPU 镜像分别预装），TensorRT dev headers/libs（GPU builder） |
| CUDA 工具链 | CUDA Toolkit 11.8（仅 GPU builder） |

### 2.2 Linux aarch64 编译容器

| 属性 | 值 |
|------|-----|
| 镜像名 | `agilestar/ai-builder-linux-arm:latest` |
| 基础镜像 | `ubuntu:22.04`（ARM 原生）或 x86 交叉编译 |
| 编译器 | aarch64-linux-gnu-g++ 12（交叉编译）/ GCC 12（原生） |
| 目标架构 | aarch64-linux-gnu |

### 2.3 Windows x86_64 / x86_32 编译容器

| 属性 | 值 |
|------|-----|
| 镜像名 | `agilestar/ai-builder-win:latest` |
| 基础镜像 | `mcr.microsoft.com/windows/servercore`（CI 环境） |
| 编译器 | MSVC 2022 (cl.exe) |
| 构建工具 | CMake + MSBuild |
| 目标架构 | x86_64（64 位）和 x86（32 位） |

### 2.4 挂载目录

| 宿主机路径 | 容器路径 | 模式 |
|-----------|---------|------|
| `./cpp/`（源码） | `/workspace/src` | 只读 |
| `/data/ai_platform/libs/<arch>/` | `/workspace/output` | 读写 |
| `/data/ai_platform/logs/build/` | `/workspace/logs` | 读写 |

---

## 3. C++ CMake 工程结构

```
cpp/
├── CMakeLists.txt                  # 顶层 CMake，聚合所有子工程
├── cmake/
│   ├── CompilerFlags.cmake         # 统一编译选项（Google 风格、警告配置）
│   ├── FindONNXRuntime.cmake       # 查找 ONNXRuntime 依赖
│   ├── FindTensorRT.cmake          # 查找 TensorRT 依赖
│   ├── FindCUDA.cmake              # 查找 CUDA 工具链
│   └── CapabilityPlugin.cmake      # 能力插件 CMake 宏（复用模板）
│
├── sdk/                            # 公共 SDK 头文件（只读，不编译为库）
│   ├── ai_capability.h             # 统一能力 C ABI 接口定义
│   ├── ai_types.h                  # 统一数据结构、错误码
│   └── ai_runtime.h                # Runtime 管理接口
│
├── runtime/                        # 通用 Runtime 库（编译为 libai_runtime.so）
│   ├── CMakeLists.txt
│   ├── include/
│   │   └── ai_runtime_impl.h
│   ├── capability_loader.cpp       # 动态加载能力 SO（dlopen/dlsym）
│   ├── instance_pool.cpp           # 推理实例池
│   ├── license_checker.cpp         # License 校验（调用授权库）
│   └── model_loader.cpp            # 模型包加载与 manifest 验证
│
├── capabilities/                   # 各 AI 能力插件（每个独立编译为 SO）
│   ├── face_detect/
│   │   ├── CMakeLists.txt          # 使用 CapabilityPlugin.cmake 宏
│   │   ├── face_detect.h
│   │   ├── face_detect.cpp         # ABI 实现
│   │   └── face_detect_impl.cpp    # 推理逻辑（ONNXRuntime）
│   ├── handwriting_reco/
│   │   └── ...
│   ├── recapture_detect/
│   │   └── ...
│   └── <new_capability>/           # 新能力按此模板创建
│
├── jni/                            # JNI 接口层（编译为 libai_jni.so）
│   ├── CMakeLists.txt
│   ├── ai_jni_bridge.cpp           # Java Native Interface 桥接
│   └── cn_agilestar_ai_AiCapability.h  # javah 生成的头文件
│
└── tests/
    └── unit/                       # 单元测试（Google Test）
        ├── CMakeLists.txt
        └── test_capability_loader.cpp
```

---

## 4. 能力插件 CMake 模板

每个新能力只需在 `CMakeLists.txt` 中调用统一宏，无需重复配置：

```cmake
# capabilities/face_detect/CMakeLists.txt

# 使用能力插件宏（定义于 cmake/CapabilityPlugin.cmake）
add_capability_plugin(
    NAME         face_detect
    SOURCES      face_detect.cpp face_detect_impl.cpp
    HEADERS      face_detect.h
    DESCRIPTION  "人脸检测 AI 能力插件"
    COMPANY      "agilestar.cn"
)
```

`CapabilityPlugin.cmake` 宏自动完成：

- 创建 shared library 目标
- 链接公共 SDK 头文件
- 链接 ONNXRuntime / TensorRT（按编译选项）
- 链接 License 校验库
- 设置标准编译选项
- 配置安装规则（输出到 `/workspace/output/`）

---

## 5. 顶层 CMake 编译选项

```cmake
# 顶层 CMakeLists.txt 主要选项
option(BUILD_GPU            "兼容旧参数；运行时 GPU 优先由能力插件自动探测" OFF)
option(ENABLE_TENSORRT      "启用编译期 TensorRT 依赖" OFF)
option(ENABLE_CUDA_KERNELS  "启用编译期 CUDA Toolkit 依赖" OFF)
option(BUILD_JNI            "构建 JNI 接口层" OFF)
option(BUILD_TESTS          "构建单元测试" OFF)
option(BUILD_ALL_CAPS       "构建所有能力插件" ON)

# 目标平台（交叉编译时由工具链文件指定）
# cmake -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain_aarch64.cmake ..
```

### 5.1 GPU 推理支持原则

**核心原则：GPU 优先，CPU 兜底**

所有能力插件在初始化时遵循以下策略：

1. **优先尝试 CUDA Execution Provider**
   - 检测 CUDA Runtime 是否可用
   - 检测 cuDNN 是否可用
   - 如果环境支持，自动使用 GPU 推理

2. **自动回退到 CPU**
   - 如果 CUDA 不可用（无 GPU/驱动/CUDA Toolkit）
   - ONNXRuntime 自动使用 CPU Execution Provider
   - 不影响推理功能，仅性能降低

3. **性能对比**
   - GPU 推理：~10-50ms（CUDA + cuDNN）
   - CPU 推理：~50-150ms（多线程优化）
   - GPU 性能提升：**3-10倍**

4. **编译要求**
   - 纯 ONNXRuntime CUDA EP 能力：**无需 CUDA Toolkit / nvcc 即可编译**
   - 生产镜像需包含 CUDA Runtime（libcudart.so）和 ONNXRuntime GPU provider
   - `BUILD_GPU` 仅为兼容旧参数；不再触发编译期 CUDA/TensorRT 探测
   - 仅当能力需要 TensorRT / 自定义 CUDA kernels 时，才显式传：
     - `-DENABLE_TENSORRT=ON`
     - `-DENABLE_CUDA_KERNELS=ON`

### 5.2 Builder 分层

| Builder | 镜像 | 适用场景 |
|---------|------|---------|
| CPU/ORT Builder | `agilestar/ai-builder-linux-x86:latest` | 默认 C++ / OpenSSL / ONNXRuntime 构建；支持运行时 GPU 优先、CPU 回退的能力 |
| GPU Builder | `agilestar/ai-builder-linux-x86-gpu:latest` | 需要 CUDA Toolkit / nvcc 的编译；与 prod 对齐 CUDA 11.8 + cuDNN 8 + ONNXRuntime GPU |

> 宿主机必须先完成 `nvidia-container-toolkit` 配置，并通过 `docker run --rm --gpus all nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 nvidia-smi` 验证容器 GPU 链路。
>
> GPU builder 除了 CUDA Toolkit / ONNXRuntime GPU 外，还会预装 TensorRT 开发头文件与库（如 `NvInfer.h`、`libnvinfer.so`），用于满足 `ENABLE_TENSORRT=ON` 的编译期依赖。

**实现示例**（所有能力插件已实现）：

```cpp
// C++ API (desktop_recapture_detect, recapture_detect)
try {
    OrtCUDAProviderOptions cuda_options;
    cuda_options.device_id = 0;
    session_opts.AppendExecutionProvider_CUDA(cuda_options);
    fprintf(stdout, "[capability] GPU mode enabled\n");
} catch (const Ort::Exception& e) {
    fprintf(stderr, "[capability] CUDA unavailable, using CPU\n");
}

// C API (face_detect)
OrtCUDAProviderOptions cuda_options;
memset(&cuda_options, 0, sizeof(cuda_options));
cuda_options.device_id = 0;
OrtStatus* status = api->SessionOptionsAppendExecutionProvider_CUDA(
    session_opts, &cuda_options);
if (status != nullptr) {
    fprintf(stderr, "[capability] CUDA unavailable, using CPU\n");
    api->ReleaseStatus(status);
}
```

---

## 6. 编译管理 Web 页面功能

| 功能 | 说明 |
|------|------|
| 能力与平台选择 | 下拉选择目标能力和目标架构（linux_x86_64 / linux_aarch64 / windows_x86_64 / windows_x86） |
| 编译选项 | 编译期 GPU 开关（`ENABLE_TENSORRT` / `ENABLE_CUDA_KERNELS`）、JNI 接口开关、Release/Debug 模式 |
| 一键编译 | 触发容器内 cmake build，实时推送编译日志（WebSocket） |
| 产物管理 | 查看历史编译版本列表，下载产物，标记正式版本 |
| 版本归档 | 自动归档到 `/workspace/output/<arch>/<capability>/<version>/` |

### 6.1 Web UI 与 Builder 诊断联动

- “新建编译任务”页面会调用 `/api/v1/builder/diagnostics`
- 前端显式展示当前 builder 的：
  - `builder_toolchain_profile`
  - `onnxruntime_package`
  - `cuda_toolkit_available`
  - `tensorrt_available`
  - `supports_compile_time_gpu_features`
- `ENABLE_TENSORRT` / `ENABLE_CUDA_KERNELS` 使用独立复选开关管理
- 前端会自动把这些开关合并进 `extra_cmake_args`，并过滤手工输入里重复的 GPU 开关

---

## 7. 编译产物归档规范

编译完成后，产物按以下结构归档：

```
/data/ai_platform/libs/
├── linux_x86_64/
│   ├── face_detect/
│   │   ├── v1.0.0/
│   │   │   ├── libface_detect.so
│   │   │   └── build_info.json    # 编译环境信息
│   │   └── current -> v1.0.0
│   └── handwriting_reco/
│       └── ...
├── linux_aarch64/
│   └── face_detect/
│       └── ...
└── windows_x86_64/
    └── face_detect/
        ├── v1.0.0/
        │   └── face_detect.dll
        └── current -> v1.0.0
```

### build_info.json 示例

```json
{
  "capability": "face_detect",
  "version": "1.0.0",
  "target_arch": "linux_x86_64",
  "compiler": "g++ 12.2.0",
  "cmake_version": "3.26.4",
  "build_type": "Release",
  "gpu_enabled": true,
  "runtime_gpu_capable": true,
  "compile_gpu_mode": "runtime_only",
  "compile_gpu_features": [],
  "build_gpu_toolchain": false,
  "builder_toolchain_profile": "cpu-ort",
  "builder_image": "agilestar/ai-builder-linux-x86:latest",
  "onnxruntime_package": "cpu",
  "cuda_toolkit_available": false,
  "tensorrt_available": false,
  "built_at": "2026-03-27T08:00:00Z",
  "built_by": "agilestar/ai-builder-linux-x86:1.0.0",
  "git_commit": "abc1234"
}
```

---

## 8. 多平台编译流程（CI/CD）

```
触发编译（Web 界面 或 CI 流水线）
        ↓
拉取对应平台的 Builder 镜像
        ↓
挂载源码目录（只读）和输出目录（读写）
        ↓
容器内执行：
  cmake -B build -S /workspace/src/cpp \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/workspace/output
  # 如需编译期 TensorRT / CUDA kernels，再显式增加：
  #   -DENABLE_TENSORRT=ON
  #   -DENABLE_CUDA_KERNELS=ON
  cmake --build build --target <capability> -- -j$(nproc)
  cmake --install build
        ↓
产物写入 /workspace/output（即宿主机 /data/ai_platform/libs/<arch>/）
        ↓
生成 build_info.json
        ↓
更新 current 符号链接（可选）
```

---

## 9. 新增 AI 能力模块开发规范（全链路更新清单）

> **重要原则**：每次新增一个 AI 能力模块时，必须同步更新所有关联子系统的代码、配置和 Web 页面。以下清单必须全部完成，确保全链路打通。

### 9.1 必须更新的内容清单

| 序号 | 子系统 | 更新内容 | 文件/目录 |
|------|--------|---------|----------|
| 1 | C++ 能力插件 | 创建能力插件源码 | `cpp/capabilities/<new_cap>/` |
| 2 | C++ CMake | 注册新能力到 CMake 编译系统 | `cpp/capabilities/<new_cap>/CMakeLists.txt` |
| 3 | 训练脚本 | 创建训练和导出脚本 | `train/scripts/<new_cap>/train.py, export.py, config.json` |
| 4 | 训练 Web 页面 | 新能力自动出现在能力配置列表（动态加载，通常无需改代码） | `train/frontend/` |
| 5 | 测试推理器 | 添加能力专属推理器实现 | `test/backend/inferencers.py` |
| 6 | 测试 Web 页面 | 新能力自动出现在模型列表（动态加载，通常无需改代码） | `test/frontend/` |
| 7 | 授权系统 | 将新能力名称添加到可选能力列表 | `license/backend/` 能力列表配置 |
| 8 | 授权 Web 页面 | 新能力出现在授权生成时的能力勾选列表 | `license/frontend/` |
| 9 | 编译 Web 页面 | 新能力自动出现在编译目标列表（动态扫描，无需改代码） | `build/frontend/` |
| 10 | 编译后端 | 新能力自动可编译（CMake 宏模板，无需改代码） | `build/backend/` |
| 11 | 生产推理服务 | 新能力 SO 和模型放置到正确位置后自动加载（热重载） | `prod/web_service/` |
| 12 | 生产 Web 页面 | 新能力自动出现在 API 测试页和状态页（动态加载） | `prod/frontend/` |
| 13 | AI 编排系统 | 新能力自动出现在编排步骤能力选择列表（动态加载） | `prod/frontend/` |
| 14 | 文档 | 更新能力清单文档 | `docs/ai_capability_market_overview.md` |

### 9.2 新增 AI 能力的标准操作步骤

```
1. 【训练准备】
   ├── 创建训练脚本: train/scripts/<new_cap>/train.py, export.py, config.json
   ├── 准备训练样本: /data/ai_platform/datasets/<new_cap>/
   └── 在训练 Web 页面配置能力并启动训练

2. 【模型导出】
   └── 训练完成后导出模型包到: /data/ai_platform/models/<new_cap>/v1.0.0/

3. 【测试验证】
   ├── 添加测试推理器: test/backend/inferencers.py (新增 <NewCap>Inferencer 类)
   ├── 准备测试样本: /data/ai_platform/datasets/<new_cap>/test/
   └── 在测试 Web 页面执行单样本和批量测试

4. 【C++ 插件开发】
   ├── 创建插件代码: cpp/capabilities/<new_cap>/<new_cap>.cpp/.h
   ├── 创建 CMakeLists.txt (使用 add_capability_plugin 宏)
   └── 单元测试: cpp/tests/test_<new_cap>.cpp

5. 【授权配置】
   └── 在授权 Web 页面生成包含新能力的试用授权

6. 【编译 SO】
   └── 在编译 Web 页面选择新能力 + 试用授权密钥对，触发编译

7. 【生产集成】
   ├── 编译产物自动归档到: /data/ai_platform/libs/<arch>/<new_cap>/
   ├── 启动/重启生产镜像
   └── 在生产 Web 页面测试新能力推理接口

8. 【AI 编排】(可选)
   └── 如需将新能力纳入编排 Pipeline，在编排管理页面创建或更新 Pipeline

9. 【文档更新】
   └── 更新 docs/ai_capability_market_overview.md 能力清单
```

### 9.3 自动化与手动更新

| 类型 | 自动适配（无需改代码） | 需手动更新 |
|------|----------------------|-----------|
| 训练 Web | ✅ 能力列表动态加载 | — |
| 测试 Web | ✅ 模型列表动态扫描 | ⚠️ 需添加推理器类 |
| 授权 Web | ✅ 能力列表动态读取 | — |
| 编译 Web | ✅ 能力列表动态扫描 | — |
| 生产 Web | ✅ 能力列表动态加载 | — |
| AI 编排 | ✅ 能力列表动态加载 | ⚠️ 需创建 Pipeline 配置（如有需要） |
| C++ 代码 | — | ⚠️ 必须创建插件源码 |
| 训练脚本 | — | ⚠️ 必须创建训练脚本 |

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
