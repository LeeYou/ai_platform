# 新增 AI 能力开发指南

> **北京爱知之星科技股份有限公司 (Agile Star)**
>
> 本文档描述在 AI 中台平台中新增一项 AI 能力的完整流程，从 C++ 插件开发到生产部署、编排集成的全链路操作规范。

---

## 目录

1. [概述](#1-概述)
2. [前置条件](#2-前置条件)
3. [步骤一：C++ 插件开发](#3-步骤一c-插件开发)
4. [步骤二：训练脚本开发](#4-步骤二训练脚本开发)
5. [步骤三：编译验证](#5-步骤三编译验证)
6. [步骤四：测试验证](#6-步骤四测试验证)
7. [步骤五：授权配置](#7-步骤五授权配置)
8. [步骤六：生产部署](#8-步骤六生产部署)
9. [步骤七：编排集成](#9-步骤七编排集成)
10. [完整检查清单](#10-完整检查清单)
11. [参考：recapture_detect 实现](#11-参考recapture_detect-实现)

---

## 1. 概述

### 1.1 能力概念

AI 中台将每一种 AI 算法抽象为一个**能力（Capability）**。每个能力是一个独立的共享库（Linux `.so` / Windows `.dll`），实现统一的 C ABI 接口，可被生产推理服务动态加载和调用。

一个完整的 AI 能力由以下部分组成：

| 组成部分 | 说明 |
|---------|------|
| C++ 插件 | 实现 ABI 接口的共享库（`lib<name>.so`） |
| 训练脚本 | PyTorch 训练 + ONNX 导出脚本 |
| 模型包 | `model.onnx` + `preprocess.json` + `manifest.json` + `labels.json` |
| 授权条目 | License 中的 `capabilities` 数组包含该能力名称 |
| 测试推理器 | 测试后端的 Python 推理器类 |
| 文档 | 能力说明文档 |

### 1.2 全链路流程

```
训练脚本开发          C++ 插件开发
    │                     │
    ▼                     ▼
 训练 Web 训练模型    编译 Web 编译 SO
    │                     │
    ▼                     ▼
 导出 model.onnx     输出 lib<name>.so
    │                     │
    ├─────────┬───────────┘
    ▼         ▼
  测试 Web 验证推理
         │
         ▼
  授权 Web 生成 License
         │
         ▼
  生产部署（模型 + SO + License）
         │
         ▼
  编排 Pipeline（可选）
```

全流程中，训练 Web、编译 Web、生产 Web、授权 Web、编排系统均**自动识别**新能力（动态扫描），开发者只需创建源码和脚本，无需修改这些子系统的代码。

---

## 2. 前置条件

### 2.1 开发环境

| 工具 | 最低版本 | 说明 |
|------|---------|------|
| GCC | 12+ | C++17 编译器 |
| CMake | 3.26+ | 构建系统 |
| ONNXRuntime | 1.18.1+ | 推理引擎 |
| Python | 3.10+ | 训练脚本 |
| PyTorch | 2.0+ | 训练框架 |
| Docker | 24+ | 容器运行 |
| Git | 2.0+ | 版本控制 |

### 2.2 目录结构

在开始之前，确认你对以下目录有写权限：

```
ai_platform/
├── cpp/capabilities/<name>/          # C++ 插件源码
├── train/scripts/<name>/             # 训练脚本
├── test/backend/inferencers.py       # 测试推理器
└── docs/                             # 文档
```

### 2.3 宿主机目录

生产和测试环境使用宿主机挂载目录：

```
/data/ai_platform/
├── datasets/<name>/                  # 训练/测试数据集
├── models/<name>/v1.0.0/             # 导出的模型包
├── libs/linux_x86_64/<name>/         # 编译产物 SO
├── licenses/                         # License 文件
├── pipelines/                        # 编排 Pipeline JSON
└── logs/                             # 各服务日志
```

---

## 3. 步骤一：C++ 插件开发

### 3.1 目录结构

在 `cpp/capabilities/` 下创建以能力名命名的目录：

```
cpp/capabilities/<name>/
├── CMakeLists.txt       # CMake 编译配置
├── <name>.h             # 内部头文件
└── <name>.cpp           # ABI 接口实现
```

### 3.2 CMakeLists.txt 模板

使用 `add_capability_plugin` 宏（定义在 `cpp/cmake/CapabilityPlugin.cmake`）注册能力。
该宏会自动完成共享库创建、依赖链接、编译选项设置和安装规则配置。

```cmake
# <name> 能力插件

add_capability_plugin(
    NAME         <name>
    SOURCES      <name>.cpp
    HEADERS      <name>.h
    DESCRIPTION  "<name> AI 能力插件"
    COMPANY      "agilestar.cn"
)
```

宏自动链接的依赖：

| 依赖 | 说明 |
|------|------|
| `ONNXRuntime::ONNXRuntime` | ONNX 推理引擎（必选） |
| `TensorRT::TensorRT` | GPU 加速（当 `BUILD_GPU=ON` 时） |
| `ai_license` | License 校验库 |

宏自动注入的编译宏：

```cpp
AI_CAPABILITY_NAME    // 能力名称字符串，如 "recapture_detect"
AI_CAPABILITY_VERSION // 能力版本，如 "1.0.0"
AI_COMPANY            // 公司标识，如 "agilestar.cn"
```

### 3.3 头文件模板

```cpp
#ifndef AGILESTAR_<NAME_UPPER>_H
#define AGILESTAR_<NAME_UPPER>_H

#include "ai_capability.h"

// 在此声明内部结构体和辅助函数

#endif /* AGILESTAR_<NAME_UPPER>_H */
```

### 3.4 ABI 接口实现

每个能力插件必须实现 `ai_capability.h` 定义的 **8 个** C ABI 导出函数：

```cpp
#include "<name>.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <memory>
#include <string>
#include <vector>
#include <atomic>

#if __has_include(<onnxruntime_cxx_api.h>)
#  include <onnxruntime_cxx_api.h>
#  define HAS_ORT 1
#else
#  define HAS_ORT 0
#endif

// ──────────────────────────────────────────────
// 内部上下文结构体
// ──────────────────────────────────────────────

struct CapabilityContext {
    std::string model_dir;
    std::string license_path;

    // 预处理参数（从 preprocess.json 加载）
    int   input_width  = 224;
    int   input_height = 224;
    float mean[3]      = {0.485f, 0.456f, 0.406f};
    float std_dev[3]   = {0.229f, 0.224f, 0.225f};

    // 推理计数器（用于周期性 License 校验）
    std::atomic<uint64_t> infer_count{0};

#if HAS_ORT
    Ort::Env                         ort_env{ORT_LOGGING_LEVEL_WARNING, "<name>"};
    std::unique_ptr<Ort::Session>    session;
    Ort::SessionOptions              session_opts;
    std::vector<std::string>         input_names_storage;
    std::vector<std::string>         output_names_storage;
    std::vector<const char*>         input_names;
    std::vector<const char*>         output_names;
#endif
};

// ──────────────────────────────────────────────
// 辅助函数
// ──────────────────────────────────────────────

static char* _dup(const char* s) {
    if (!s) return nullptr;
    size_t len = std::strlen(s);
    char*  buf = static_cast<char*>(std::malloc(len + 1));
    if (buf) std::memcpy(buf, s, len + 1);
    return buf;
}

static void _set_result(AiResult* result, int32_t code,
                         const char* json, const char* msg = nullptr) {
    if (!result) return;
    result->error_code  = code;
    result->json_result = json ? _dup(json) : nullptr;
    result->result_len  = json ? static_cast<int32_t>(std::strlen(json)) : 0;
    result->error_msg   = msg  ? _dup(msg)  : nullptr;
}

// ──────────────────────────────────────────────
// ABI 接口实现
// ──────────────────────────────────────────────

AI_EXPORT int32_t AiGetAbiVersion(void) {
    return AI_ABI_VERSION;  // 当前版本 10000 (v1.0.0)
}

AI_EXPORT AiHandle AiCreate(const char* model_dir, const char* /*config_json*/) {
    if (!model_dir) return nullptr;
    auto* ctx = new CapabilityContext();
    ctx->model_dir = model_dir;
    // TODO: 从 preprocess.json 加载预处理参数
    return static_cast<AiHandle>(ctx);
}

AI_EXPORT int32_t AiInit(AiHandle handle) {
    if (!handle) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<CapabilityContext*>(handle);

    // License 校验
    std::string license_path = ctx->model_dir + "/../../../licenses/license.bin";
    const char* env_lic = std::getenv("AI_LICENSE_PATH");
    if (env_lic) license_path = env_lic;
    ctx->license_path = license_path;
    // TODO: 调用 _check_license_capability(license_path) 校验能力授权

#if HAS_ORT
    // 加载 ONNX 模型
    std::string model_path = ctx->model_dir + "/model.onnx";
    ctx->session_opts.SetIntraOpNumThreads(1);
    ctx->session_opts.SetGraphOptimizationLevel(ORT_ENABLE_EXTENDED);

    try {
        ctx->session = std::make_unique<Ort::Session>(
            ctx->ort_env, model_path.c_str(), ctx->session_opts);
    } catch (const Ort::Exception& ex) {
        std::fprintf(stderr, "[<name>] Failed to load model %s: %s\n",
                     model_path.c_str(), ex.what());
        return AI_ERR_LOAD_FAILED;
    }

    // 缓存输入/输出名称
    Ort::AllocatorWithDefaultOptions alloc;
    for (size_t i = 0; i < ctx->session->GetInputCount(); ++i)
        ctx->input_names_storage.push_back(
            ctx->session->GetInputNameAllocated(i, alloc).get());
    for (size_t i = 0; i < ctx->session->GetOutputCount(); ++i)
        ctx->output_names_storage.push_back(
            ctx->session->GetOutputNameAllocated(i, alloc).get());
    for (auto& s : ctx->input_names_storage)  ctx->input_names.push_back(s.c_str());
    for (auto& s : ctx->output_names_storage) ctx->output_names.push_back(s.c_str());
#endif

    return AI_OK;
}

AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
    if (!handle || !input || !output) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<CapabilityContext*>(handle);

#if HAS_ORT
    if (!ctx->session) {
        _set_result(output, AI_ERR_LOAD_FAILED, nullptr, "Model not loaded");
        return AI_ERR_LOAD_FAILED;
    }

    // TODO: 实现预处理（缩放、归一化、NHWC→NCHW 转换）
    // TODO: 创建输入 Tensor 并调用 session->Run()
    // TODO: 解析输出 Tensor 并构造 JSON 结果

    _set_result(output, AI_OK, "{\"result\": \"TODO\"}");
    return AI_OK;
#else
    _set_result(output, AI_OK,
        "{\"result\": \"stub\", \"note\": \"ONNXRuntime not available\"}");
    return AI_OK;
#endif
}

AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir) {
    if (!handle || !new_model_dir) return AI_ERR_INVALID_PARAM;
    // 创建新实例、初始化、交换内部状态、销毁旧实例
    AiHandle new_h = AiCreate(new_model_dir, nullptr);
    if (!new_h) return AI_ERR_LOAD_FAILED;
    int32_t rc = AiInit(new_h);
    if (rc != AI_OK) { AiDestroy(new_h); return rc; }

    auto* ctx     = static_cast<CapabilityContext*>(handle);
    auto* new_ctx = static_cast<CapabilityContext*>(new_h);
#if HAS_ORT
    ctx->session              = std::move(new_ctx->session);
    ctx->input_names_storage  = std::move(new_ctx->input_names_storage);
    ctx->output_names_storage = std::move(new_ctx->output_names_storage);
    ctx->input_names          = std::move(new_ctx->input_names);
    ctx->output_names         = std::move(new_ctx->output_names);
#endif
    ctx->model_dir    = new_ctx->model_dir;
    ctx->input_width  = new_ctx->input_width;
    ctx->input_height = new_ctx->input_height;
    ctx->infer_count  = 0;
    AiDestroy(new_h);
    return AI_OK;
}

AI_EXPORT int32_t AiGetInfo(AiHandle /*handle*/, char* info_buf, int32_t buf_len) {
    static const char kInfo[] =
        "{\"capability\":\"<name>\","
        "\"capability_name_cn\":\"<能力中文名>\","
        "\"abi_version\":\"10000\","
        "\"company\":\"agilestar.cn\"}";
    int32_t needed = static_cast<int32_t>(std::strlen(kInfo));
    if (!info_buf || buf_len <= needed) return needed;
    std::memcpy(info_buf, kInfo, static_cast<size_t>(needed) + 1);
    return needed;
}

AI_EXPORT void AiDestroy(AiHandle handle) {
    if (!handle) return;
    delete static_cast<CapabilityContext*>(handle);
}

AI_EXPORT void AiFreeResult(AiResult* result) {
    if (!result) return;
    std::free(result->json_result);
    std::free(result->error_msg);
    result->json_result = nullptr;
    result->error_msg   = nullptr;
    result->result_len  = 0;
}
```

### 3.5 ABI 接口说明

| 函数 | 签名 | 说明 |
|------|------|------|
| `AiGetAbiVersion` | `int32_t ()` | 返回 ABI 版本号（`10000` = v1.0.0），Runtime 用于兼容性检查 |
| `AiCreate` | `AiHandle (model_dir, config_json)` | 创建实例，分配内部数据结构，不加载模型 |
| `AiInit` | `int32_t (handle)` | 初始化实例：加载模型、校验 License、预热引擎 |
| `AiInfer` | `int32_t (handle, input, output)` | 执行单次推理，同一 handle 不可并发调用 |
| `AiReload` | `int32_t (handle, new_model_dir)` | 热重载模型，无需销毁重建实例 |
| `AiGetInfo` | `int32_t (handle, buf, len)` | 获取能力元信息（JSON） |
| `AiDestroy` | `void (handle)` | 销毁实例，释放全部资源 |
| `AiFreeResult` | `void (result)` | 释放推理结果内存（json\_result + error\_msg） |

### 3.6 关键数据结构

```c
// 不透明实例句柄
typedef void* AiHandle;

// 输入图像
typedef struct {
    const uint8_t* data;       // 原始字节数据
    int32_t        width;      // 宽度（像素）
    int32_t        height;     // 高度（像素）
    int32_t        channels;   // 通道数：1=灰度, 3=BGR/RGB
    int32_t        data_type;  // 0=uint8, 1=float32
    int32_t        color_format; // 0=BGR, 1=RGB, 2=GRAY
    int32_t        stride;     // 每行字节数；0 = width * channels
} AiImage;

// 推理结果
typedef struct {
    char*   json_result; // UTF-8 JSON 结果（插件分配）
    int32_t result_len;  // json_result 字节长度
    int32_t error_code;  // 0=成功，非 0 见 AiErrorCode
    char*   error_msg;   // 错误描述（插件分配，可为 NULL）
} AiResult;
```

### 3.7 错误码

| 错误码 | 枚举值 | 说明 |
|--------|--------|------|
| 0 | `AI_OK` | 成功 |
| 1001 | `AI_ERR_INVALID_PARAM` | 参数无效 |
| 1002 | `AI_ERR_IMAGE_DECODE` | 图像解码失败 |
| 2001 | `AI_ERR_CAPABILITY_MISSING` | 能力不存在 |
| 2002 | `AI_ERR_LOAD_FAILED` | SO 加载失败 |
| 2003 | `AI_ERR_MODEL_CORRUPT` | 模型文件损坏 |
| 2004 | `AI_ERR_INFER_FAILED` | 推理执行错误 |
| 4001 | `AI_ERR_LICENSE_INVALID` | License 签名验证失败 |
| 4002 | `AI_ERR_LICENSE_EXPIRED` | License 已过期 |
| 4003 | `AI_ERR_LICENSE_MISMATCH` | 机器指纹不匹配 |
| 4004 | `AI_ERR_CAP_NOT_LICENSED` | 能力未授权 |
| 5001 | `AI_ERR_INTERNAL` | 内部错误 |

### 3.8 ONNXRuntime 集成要点

1. **条件编译**：使用 `__has_include(<onnxruntime_cxx_api.h>)` 检测 ORT 是否可用，不可用时输出 stub 结果
2. **Session 创建**：在 `AiInit` 中创建 `Ort::Session`，配置线程数和图优化级别
3. **预处理**：在 `AiInfer` 中将输入图像从 NHWC uint8 BGR 转为 NCHW float32 RGB，应用 mean/std 归一化
4. **Tensor 创建**：使用 `Ort::Value::CreateTensor<float>()` 创建输入张量
5. **推理执行**：调用 `session->Run()` 并在 try-catch 中捕获 `Ort::Exception`
6. **内存管理**：`json_result` 和 `error_msg` 通过 `std::malloc` 分配，由 `AiFreeResult` 释放，不得跨 SO 调用 `free()`

---

## 3A. 样本标注（可选但推荐）

在训练之前，可使用训练容器内置的样本标注功能对原始数据集进行标注：

1. 在训练 Web 的**样本标注**页面创建标注项目，关联新能力和标注类型
2. 在标注工作台完成样本标注（支持二分类、多分类、目标检测、OCR、图像分割）
3. 导出标注结果为训练兼容格式（分类目录结构 / YOLO txt / OCR txt）

详细标注操作见 `docs/design/annotation_service.md`。

---

## 4. 步骤二：训练脚本开发

### 4.1 目录结构

在 `train/scripts/` 下创建以能力名命名的目录：

```
train/scripts/<name>/
├── train.py           # 训练入口
├── export.py          # ONNX 导出
├── config.json        # 超参数配置
├── requirements.txt   # Python 依赖
└── README.md          # 说明文档（可选）
```

### 4.2 config.json 模板

```json
{
  "capability": "<name>",
  "capability_name_cn": "<能力中文名>",
  "model_arch": "<模型架构描述>",
  "input_size": [224, 224],
  "batch_size": 32,
  "epochs": 50,
  "lr0": 0.01,
  "lrf": 0.001,
  "momentum": 0.937,
  "weight_decay": 0.0005,
  "warmup_epochs": 3,
  "augment": true,
  "workers": 4,
  "device": "auto",
  "amp": true,
  "patience": 20,
  "val_split": 0.1,
  "preprocessing": {
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
    "normalize": true,
    "color_format": "RGB"
  }
}
```

### 4.3 train.py 约定

```python
"""Train <name> (<能力中文名>).

Architecture: <模型架构>

Usage:
    python train.py --config config.json \
                    --dataset /workspace/datasets/<name>/ \
                    --output /workspace/models/<name>/v1.0.0/ \
                    --version 1.0.0

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time

_stop_requested = False


def _handle_sigterm(signum, frame):
    global _stop_requested
    _stop_requested = True
    print("[INFO] SIGTERM received — stopping after current epoch.", flush=True)


signal.signal(signal.SIGTERM, _handle_sigterm)


def _parse_args():
    p = argparse.ArgumentParser(description="Train <name>")
    p.add_argument("--config",  default="config.json")
    p.add_argument("--dataset", default="/workspace/datasets/<name>/")
    p.add_argument("--output",  default="/workspace/models/<name>/v1.0.0/")
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--resume",  default=None)
    return p.parse_args()


def main():
    args = _parse_args()
    config = {}
    if os.path.exists(args.config):
        config = json.load(open(args.config, encoding="utf-8"))

    print(f"[INFO] Starting training: <name> v{args.version}", flush=True)
    print(f"[INFO] Dataset: {args.dataset}", flush=True)
    print(f"[INFO] Output:  {args.output}", flush=True)

    # TODO: 实现真实训练逻辑
    #   1. 加载数据集
    #   2. 构建模型
    #   3. 训练循环（支持 SIGTERM 优雅停止和 early stopping）
    #   4. 保存 best.pt 和 last.pt 到 args.output


if __name__ == "__main__":
    main()
```

**关键约定**：
- 命令行参数必须包含 `--config`、`--dataset`、`--output`、`--version`
- 支持 `--resume` 断点续训
- 必须处理 `SIGTERM` 信号（训练 Web 通过 SIGTERM 停止训练）
- 每个 epoch 输出格式化日志：`[EPOCH {n}/{total}] loss=... accuracy=...`
- 训练产物保存到 `args.output`（包含 `best.pt` 和 `last.pt`）

### 4.4 export.py 约定

```python
"""Export <name> (<能力中文名>) model to ONNX format.

Usage:
    python export.py --output /workspace/models/<name>/v1.0.0/ --version 1.0.0

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _parse_args():
    p = argparse.ArgumentParser(description="Export <name> to ONNX")
    p.add_argument("--output",     default="/workspace/models/<name>/v1.0.0/")
    p.add_argument("--version",    default="1.0.0")
    p.add_argument("--checkpoint", default=None)
    return p.parse_args()


def _write_preprocess_json(output_path: str) -> None:
    """生成 C++ 插件所需的预处理配置。"""
    data = {
        "resize": {"width": 224, "height": 224, "keep_ratio": False},
        "pad_value": [114, 114, 114],
        "normalize": True,
        "mean": [0.485, 0.456, 0.406],
        "std":  [0.229, 0.224, 0.225],
        "color_convert": "BGR2RGB",
    }
    path = os.path.join(output_path, "preprocess.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[EXPORT] preprocess.json → {path}", flush=True)


def _write_labels_json(output_path: str) -> None:
    """生成标签映射文件。"""
    data = {
        "labels": ["class_0", "class_1"],
        "num_classes": 2,
    }
    path = os.path.join(output_path, "labels.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[EXPORT] labels.json → {path}", flush=True)


def main():
    args = _parse_args()
    os.makedirs(args.output, exist_ok=True)

    import torch

    # 定位 checkpoint
    ckpt_path = args.checkpoint
    if not ckpt_path:
        for fname in ("best.pt", "last.pt"):
            candidate = os.path.join(args.output, fname)
            if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                ckpt_path = candidate
                break
    if not ckpt_path:
        print("[ERROR] No checkpoint found. Run train.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"[EXPORT] Loading checkpoint: {ckpt_path}", flush=True)

    # TODO: 替换为真实模型类
    import torch.nn as nn
    model = nn.Sequential(nn.Flatten(), nn.Linear(150528, 2))
    ckpt = torch.load(ckpt_path, map_location="cpu")
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
    model.eval()

    # 导出 ONNX
    onnx_path = os.path.join(args.output, "model.onnx")
    dummy = torch.zeros(1, 3, 224, 224)
    torch.onnx.export(
        model, dummy, onnx_path,
        opset_version=17,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )
    print(f"[EXPORT] ONNX → {onnx_path}", flush=True)

    _write_preprocess_json(args.output)
    _write_labels_json(args.output)
    print("[EXPORT] Done", flush=True)


if __name__ == "__main__":
    main()
```

导出后模型包目录结构：

```
/data/ai_platform/models/<name>/v1.0.0/
├── model.onnx           # ONNX 模型文件
├── preprocess.json      # 预处理参数（C++ 插件读取）
├── labels.json          # 标签映射
├── best.pt              # PyTorch checkpoint
└── last.pt              # 最后一次 checkpoint
```

### 4.5 requirements.txt 模板

```
torch>=2.0
torchvision>=0.15
onnxruntime>=1.17
numpy>=1.24
opencv-python-headless>=4.8
Pillow>=10.0
```

---

## 5. 步骤三：编译验证

### 5.1 编译 Web 自动发现

编译后端（`build/backend/`）通过扫描 `cpp/capabilities/` 目录自动发现所有能力。只要在该目录下创建了符合规范的 CMakeLists.txt，新能力就会自动出现在编译 Web 页面的编译目标列表中。

### 5.2 触发编译

1. 打开编译 Web 页面（默认端口 `8004`）
2. 在编译目标列表中找到新能力（自动出现）
3. 选择目标平台（`linux_x86_64` / `linux_aarch64`）
4. 点击**编译**按钮触发构建
5. 编译完成后，SO 文件会自动归档到：

```
/data/ai_platform/libs/linux_x86_64/<name>/lib<name>.so
```

### 5.3 验证编译产物

```bash
# 确认 SO 文件存在且导出了 ABI 函数
ls -la /data/ai_platform/libs/linux_x86_64/<name>/lib<name>.so

# 检查导出符号
nm -D /data/ai_platform/libs/linux_x86_64/<name>/lib<name>.so | grep -E "Ai(Create|Init|Infer|Reload|Destroy|FreeResult|GetInfo|GetAbiVersion)"
```

预期输出应包含以下 8 个符号（类型为 `T`）：

```
T AiCreate
T AiDestroy
T AiFreeResult
T AiGetAbiVersion
T AiGetInfo
T AiInfer
T AiInit
T AiReload
```

---

## 6. 步骤四：测试验证

### 6.1 测试推理器

测试后端（`test/backend/`）根据模型包中的 `manifest.json` 自动发现可测试的模型。但需要为新能力添加一个推理器类。

在 `test/backend/inferencers.py` 中添加推理器类：

```python
class <CapName>Inferencer(BaseInferencer):
    """<能力中文名> — <输出描述>."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        # TODO: 根据模型输出格式实现后处理逻辑
        # 例如二分类：
        if len(out) >= 2:
            exp = np.exp(out - out.max())
            prob = exp / exp.sum()
            return {
                "label": "positive" if prob[1] > 0.5 else "negative",
                "score": round(float(prob[1]), 4),
            }
        score = float(1 / (1 + np.exp(-out[0])))
        return {"label": "positive" if score > 0.5 else "negative", "score": round(score, 4)}
```

### 6.2 单样本测试

1. 打开测试 Web 页面（默认端口 `8002`）
2. 选择对应能力和模型版本
3. 上传测试图像
4. 查看推理结果 JSON

### 6.3 批量测试

1. 准备测试数据集到 `/data/ai_platform/datasets/<name>/test/`
2. 在测试 Web 页面选择**批量测试**模式
3. 选择数据集目录，启动批量推理
4. 查看准确率、耗时等统计信息

---

## 7. 步骤五：授权配置

### 7.1 License 能力注册

授权 Web 页面（默认端口 `8003`）会动态读取可选能力列表。要在 License 中启用新能力，只需在授权 Web 页面生成 License 时勾选新能力名称。

License JSON 结构中的 `capabilities` 数组示例：

```json
{
  "license_id": "xxxx-xxxx-xxxx",
  "customer": "客户名称",
  "capabilities": [
    "face_detect",
    "face_recognition",
    "<name>"
  ],
  "expire_date": "2027-12-31",
  "machine_fingerprint": "..."
}
```

### 7.2 C++ 插件中的 License 校验

C++ 插件在 `AiInit` 时读取 `license.bin` 文件并检查 `capabilities` 数组中是否包含当前能力名称。插件还会每 1000 次推理周期性校验 License 有效性。

```cpp
// AiInit 中的校验逻辑
std::string license_path = ctx->model_dir + "/../../../licenses/license.bin";
const char* env_lic = std::getenv("AI_LICENSE_PATH");
if (env_lic) license_path = env_lic;

if (!_check_license_capability(license_path)) {
    // 开发/测试模式下发出警告但继续运行
    std::fprintf(stderr, "[<name>] WARNING: License check failed\n");
}
```

---

## 8. 步骤六：生产部署

### 8.1 部署文件

生产推理服务需要以下文件：

```
/data/ai_platform/
├── models/<name>/v1.0.0/       # 模型包（model.onnx + preprocess.json + ...）
├── libs/linux_x86_64/<name>/   # 编译产物（lib<name>.so）
└── licenses/license.bin        # 包含该能力的 License 文件
```

### 8.2 启动/热重载

生产推理服务（`prod/web_service/`）支持**热重载**，无需重启容器：

1. **首次部署**：将模型包和 SO 文件放置到上述路径，启动生产容器

   ```bash
   cd deploy/
   docker compose -f docker-compose.prod.yml up -d
   ```

2. **热重载模型**：替换模型文件后，通过 API 触发重载

   ```bash
   # 通过生产 Web API 触发热重载
   curl -X POST http://localhost:8080/api/v1/capabilities/<name>/reload \
     -H "Authorization: Bearer $AI_ADMIN_TOKEN"
   ```

3. **验证部署**：调用推理接口确认新能力可用

   ```bash
   curl -X POST http://localhost:8080/api/v1/infer/<name> \
     -F "image=@test.jpg"
   ```

### 8.3 生产容器挂载

生产 Docker Compose 配置中的卷挂载：

```yaml
volumes:
  - /data/ai_platform/models:/mnt/ai_platform/models:ro
  - /data/ai_platform/libs:/mnt/ai_platform/libs:ro
  - /data/ai_platform/licenses:/mnt/ai_platform/licenses:ro
  - /data/ai_platform/pipelines:/mnt/ai_platform/pipelines:ro
  - /data/ai_platform/logs/prod:/mnt/ai_platform/logs:rw
```

生产 Web 页面（默认端口 `8080`）会自动显示新能力的 API 测试页和状态信息。

---

## 9. 步骤七：编排集成

### 9.1 Pipeline 概念

AI 编排系统允许将多个能力组合为一个 Pipeline，按步骤串行执行。每个步骤调用一个能力，可设置执行条件和失败策略。

### 9.2 创建 Pipeline JSON

在 `/data/ai_platform/pipelines/` 目录创建 Pipeline JSON 文件：

```json
{
  "pipeline_id": "my_pipeline",
  "name": "我的检测流水线",
  "description": "串行执行能力 A → 能力 B → 新能力，完成多步验证",
  "enabled": true,
  "steps": [
    {
      "step_id": "step_a",
      "capability": "face_detect",
      "description": "检测输入图像中的人脸区域",
      "params": {},
      "on_failure": "abort"
    },
    {
      "step_id": "step_b",
      "capability": "<name>",
      "description": "<新能力描述>",
      "params": {},
      "condition": "${step_a.face_count} > 0",
      "on_failure": "abort"
    }
  ],
  "output_mapping": {
    "face_detected": "${step_a.face_count} > 0",
    "final_result": "${step_b.<result_field>}"
  }
}
```

### 9.3 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `pipeline_id` | string | Pipeline 唯一标识符 |
| `name` | string | 显示名称 |
| `description` | string | 描述说明 |
| `enabled` | boolean | 是否启用 |
| `steps[].step_id` | string | 步骤 ID（Pipeline 内唯一） |
| `steps[].capability` | string | 调用的能力名称 |
| `steps[].params` | object | 传递给能力的额外参数 |
| `steps[].condition` | string | 执行条件（引用前序步骤输出，如 `${step_a.field} > 0`） |
| `steps[].on_failure` | string | 失败策略：`abort`（终止）/ `skip`（跳过）/ `default`（使用默认值） |
| `output_mapping` | object | 最终输出字段映射（引用步骤输出） |

### 9.4 参考示例：活体检测 Pipeline

以下是平台预置的「指令活体检测」Pipeline，包含 `face_detect` → `face_liveness_action` → `recapture_detect` 三步串行执行：

```json
{
  "pipeline_id": "active_liveness_check",
  "name": "指令活体检测",
  "description": "串行执行人脸检测 → 指令活体 → 翻拍检测，完成多因子活体验证",
  "enabled": true,
  "steps": [
    {
      "step_id": "detect_face",
      "capability": "face_detect",
      "description": "检测输入图像中的人脸区域",
      "params": {},
      "on_failure": "abort"
    },
    {
      "step_id": "action_liveness",
      "capability": "face_liveness_action",
      "description": "指令动作活体检测（张嘴/点头/摇头等）",
      "params": {},
      "condition": "${detect_face.face_count} > 0",
      "on_failure": "abort"
    },
    {
      "step_id": "anti_recapture",
      "capability": "recapture_detect",
      "description": "翻拍检测，排除屏幕翻拍攻击",
      "params": {},
      "condition": "${action_liveness.is_live} == true",
      "on_failure": "abort"
    }
  ],
  "output_mapping": {
    "face_detected": "${detect_face.face_count} > 0",
    "action_liveness_pass": "${action_liveness.is_live}",
    "recapture_safe": "${anti_recapture.is_real}",
    "final_result": "${anti_recapture.is_real}"
  }
}
```

也可以在生产 Web 页面的**编排管理**界面通过 GUI 创建和编辑 Pipeline。

---

## 10. 完整检查清单

> 来自 `docs/design/build_service.md` 第 9 节定义的 14 项全链路更新清单。

| 序号 | 子系统 | 更新内容 | 文件/目录 | 手动/自动 |
|------|--------|---------|----------|----------|
| 1 | C++ 能力插件 | 创建能力插件源码 | `cpp/capabilities/<name>/` | ⚠️ 手动 |
| 2 | C++ CMake | 注册新能力到 CMake 编译系统 | `cpp/capabilities/<name>/CMakeLists.txt` | ⚠️ 手动 |
| 3 | 训练脚本 | 创建训练和导出脚本 | `train/scripts/<name>/train.py, export.py, config.json` | ⚠️ 手动 |
| 4 | 训练 Web 页面 | 新能力自动出现在能力配置列表 | `train/frontend/` | ✅ 自动 |
| 5 | 测试推理器 | 添加能力专属推理器实现 | `test/backend/inferencers.py` | ⚠️ 手动 |
| 6 | 测试 Web 页面 | 新能力自动出现在模型列表 | `test/frontend/` | ✅ 自动 |
| 7 | 授权系统 | 将新能力名称添加到可选能力列表 | `license/backend/` 能力列表配置 | ✅ 自动 |
| 8 | 授权 Web 页面 | 新能力出现在授权生成时的能力勾选列表 | `license/frontend/` | ✅ 自动 |
| 9 | 编译 Web 页面 | 新能力自动出现在编译目标列表 | `build/frontend/` | ✅ 自动 |
| 10 | 编译后端 | 新能力自动可编译（CMake 宏模板） | `build/backend/` | ✅ 自动 |
| 11 | 生产推理服务 | SO + 模型放置后自动加载（热重载） | `prod/web_service/` | ✅ 自动 |
| 12 | 生产 Web 页面 | 新能力自动出现在 API 测试页和状态页 | `prod/frontend/` | ✅ 自动 |
| 13 | AI 编排系统 | 新能力自动出现在编排步骤能力选择列表 | `prod/frontend/` | ✅ 自动 |
| 14 | 文档 | 更新能力清单文档 | `docs/ai_capability_market_overview.md` | ⚠️ 手动 |

**小结**：14 项中仅 **5 项**需要手动创建代码/脚本（序号 1、2、3、5、14），其余 **9 项**均由平台自动适配。

### 标准操作步骤

```
1. 【训练准备】
   ├── 创建训练脚本: train/scripts/<name>/train.py, export.py, config.json
   ├── 准备训练样本: /data/ai_platform/datasets/<name>/
   └── 在训练 Web 页面配置能力并启动训练

2. 【模型导出】
   └── 训练完成后导出模型包到: /data/ai_platform/models/<name>/v1.0.0/

3. 【测试验证】
   ├── 添加测试推理器: test/backend/inferencers.py
   ├── 准备测试样本: /data/ai_platform/datasets/<name>/test/
   └── 在测试 Web 页面执行单样本和批量测试

4. 【C++ 插件开发】
   ├── 创建插件代码: cpp/capabilities/<name>/<name>.cpp/.h
   ├── 创建 CMakeLists.txt（使用 add_capability_plugin 宏）
   └── 单元测试: cpp/tests/test_<name>.cpp

5. 【授权配置】
   └── 在授权 Web 页面生成包含新能力的试用授权

6. 【编译 SO】
   └── 在编译 Web 页面选择新能力 + 试用授权密钥对，触发编译

7. 【生产集成】
   ├── 编译产物自动归档到: /data/ai_platform/libs/<arch>/<name>/
   ├── 启动/重启生产镜像
   └── 在生产 Web 页面测试新能力推理接口

8. 【AI 编排】(可选)
   └── 如需将新能力纳入编排 Pipeline，在编排管理页面创建或更新 Pipeline

9. 【文档更新】
   └── 更新 docs/ai_capability_market_overview.md 能力清单
```

---

## 11. 参考：recapture_detect 实现

`recapture_detect`（翻拍检测）是一个完整的参考实现，演示了二分类能力的全链路开发。

### 11.1 功能说明

翻拍检测判断输入图像是否为屏幕翻拍（recaptured）而非真实拍摄（genuine），输出二分类结果：

```json
{
  "is_recaptured": false,
  "score_genuine": 0.9234,
  "score_recaptured": 0.0766
}
```

### 11.2 目录结构

```
cpp/capabilities/recapture_detect/
├── CMakeLists.txt          # 3 行宏调用
├── recapture_detect.h      # 头文件（仅 #include "ai_capability.h"）
└── recapture_detect.cpp    # 412 行完整 ABI 实现
```

### 11.3 CMakeLists.txt

```cmake
# recapture_detect 能力插件
# Phase 3 (recapture_detect) / Phase 6 (其余能力) 实现

add_capability_plugin(
    NAME         recapture_detect
    SOURCES      recapture_detect.cpp
    HEADERS      recapture_detect.h
    DESCRIPTION  "recapture_detect AI 能力插件"
    COMPANY      "agilestar.cn"
)
```

### 11.4 核心实现要点

#### 内部上下文

```cpp
struct RecaptureContext {
    std::string model_dir;
    std::string license_path;

    int   input_width  = 224;
    int   input_height = 224;
    float mean[3]      = {0.485f, 0.456f, 0.406f};
    float std_dev[3]   = {0.229f, 0.224f, 0.225f};

    std::atomic<uint64_t> infer_count{0};

#if HAS_ORT
    Ort::Env                         ort_env{ORT_LOGGING_LEVEL_WARNING, "recapture_detect"};
    std::unique_ptr<Ort::Session>    session;
    Ort::SessionOptions              session_opts;
    std::vector<std::string>         input_names_storage;
    std::vector<std::string>         output_names_storage;
    std::vector<const char*>         input_names;
    std::vector<const char*>         output_names;
#endif
};
```

#### 预处理

图像预处理实现了不依赖 OpenCV 的双线性插值缩放：

- 输入：NHWC uint8 BGR 原始图像
- 输出：NCHW float32 RGB 归一化张量
- 步骤：BGR→RGB 转换 → 双线性缩放到 224×224 → /255.0 → (val - mean) / std

#### 推理输出解析

支持两种模型输出格式：
- **两类 softmax**：输出 2 个值 `[genuine_score, recaptured_score]`
- **单 logit**：输出 1 个值，通过 sigmoid 映射为概率

```cpp
if (n >= 2) {
    score_genuine = data[0];
    score_recaptured = data[1];
} else if (n == 1) {
    float s = 1.0f / (1.0f + std::exp(-data[0]));
    score_genuine = 1.0f - s;
    score_recaptured = s;
}
```

#### 热重载

`AiReload` 通过创建新实例并交换内部状态实现原子级模型替换：

```cpp
AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir) {
    AiHandle new_h = AiCreate(new_model_dir, nullptr);
    int32_t rc = AiInit(new_h);
    if (rc != AI_OK) { AiDestroy(new_h); return rc; }
    // 交换 session 和元数据
    auto* ctx     = static_cast<RecaptureContext*>(handle);
    auto* new_ctx = static_cast<RecaptureContext*>(new_h);
    ctx->session = std::move(new_ctx->session);
    // ... 交换其他字段
    AiDestroy(new_h);
    return AI_OK;
}
```

#### License 校验

- `AiInit` 时进行首次 License 校验
- 每 1000 次推理周期性重新校验
- 开发/测试模式下校验失败仅发出警告，不阻断推理
- License 路径可通过 `AI_LICENSE_PATH` 环境变量覆盖

### 11.5 Pipeline 中的使用

`recapture_detect` 在平台预置的活体检测 Pipeline 中作为最后一步，排除屏幕翻拍攻击：

```
face_detect → face_liveness_action → recapture_detect
              (或 face_liveness_silent)
```

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
