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
| 镜像名 | `agilestar/ai-builder-linux-x86:latest` |
| 基础镜像 | `ubuntu:22.04` |
| 编译器 | GCC 12 / G++ 12 |
| CMake 版本 | ≥3.26 |
| 推理框架 | ONNXRuntime 1.16（预装），TensorRT 8.6（可选） |
| CUDA 工具链 | CUDA Toolkit 12.1（用于 GPU 推理 SO） |

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
option(BUILD_GPU        "启用 GPU 推理（需要 CUDA + TensorRT）" OFF)
option(BUILD_JNI        "构建 JNI 接口层" OFF)
option(BUILD_TESTS      "构建单元测试" OFF)
option(BUILD_ALL_CAPS   "构建所有能力插件" ON)

# 目标平台（交叉编译时由工具链文件指定）
# cmake -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain_aarch64.cmake ..
```

---

## 6. 编译管理 Web 页面功能

| 功能 | 说明 |
|------|------|
| 能力与平台选择 | 下拉选择目标能力和目标架构（linux_x86_64 / linux_aarch64 / windows_x86_64 / windows_x86） |
| 编译选项 | GPU 支持开关、JNI 接口开关、Release/Debug 模式 |
| 一键编译 | 触发容器内 cmake build，实时推送编译日志（WebSocket） |
| 产物管理 | 查看历史编译版本列表，下载产物，标记正式版本 |
| 版本归档 | 自动归档到 `/workspace/output/<arch>/<capability>/<version>/` |

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
  "onnxruntime_version": "1.16.0",
  "tensorrt_version": "8.6.1",
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
        -DBUILD_GPU=ON \
        -DCMAKE_INSTALL_PREFIX=/workspace/output
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

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
