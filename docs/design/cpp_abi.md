# C++ ABI 接口规范

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-27**

---

## 1. 概述

本文档定义 AI 能力插件 SO/DLL 的统一 C ABI 接口规范。所有 AI 能力插件必须严格遵守此规范，以保证跨平台、跨语言（Java JNI、Python ctypes）的互操作性和接口长期稳定性。

---

## 2. 设计原则

- **纯 C 接口**：不暴露 C++ 类、模板、STL 等，保证 ABI 稳定
- **Handle 模式**：通过不透明指针（Handle）管理实例生命周期，支持多实例并发
- **内存所有权清晰**：调用方提供输入内存，插件分配输出内存，调用方通过 `AiFreeResult` 释放
- **线程安全**：同一 Handle 不可被多线程并发调用；不同 Handle 之间线程安全
- **错误码统一**：所有接口通过返回值传递错误码，不抛出 C++ 异常穿透 ABI 边界

---

## 3. 核心数据结构

### 3.1 ai_types.h

```c
#ifndef AGILESTAR_AI_TYPES_H
#define AGILESTAR_AI_TYPES_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 不透明 Handle，各 SO 内部实现 */
typedef void* AiHandle;

/* 输入图像结构 */
typedef struct {
    const uint8_t* data;    /* 图像字节数据，调用方持有，不得释放 */
    int32_t        width;   /* 图像宽度（像素） */
    int32_t        height;  /* 图像高度（像素） */
    int32_t        channels; /* 通道数：1=灰度, 3=BGR/RGB */
    int32_t        data_type; /* 0=uint8, 1=float32 */
    int32_t        color_format; /* 0=BGR, 1=RGB, 2=GRAY */
    int32_t        stride;  /* 每行字节数，0 表示 width*channels */
} AiImage;

/* 推理结果结构 */
typedef struct {
    char*   json_result;  /* JSON 格式结果，由插件分配，调用方通过 AiFreeResult 释放 */
    int32_t result_len;   /* json_result 字节长度（不含 \0） */
    int32_t error_code;   /* 0=成功，非0见错误码表 */
    char*   error_msg;    /* 错误描述，由插件分配，随 AiFreeResult 一起释放 */
} AiResult;

/* 错误码定义 */
typedef enum {
    AI_OK                     = 0,
    AI_ERR_INVALID_PARAM      = 1001,
    AI_ERR_IMAGE_DECODE       = 1002,
    AI_ERR_CAPABILITY_MISSING = 2001,
    AI_ERR_LOAD_FAILED        = 2002,
    AI_ERR_MODEL_CORRUPT      = 2003,
    AI_ERR_INFER_FAILED       = 2004,
    AI_ERR_LICENSE_INVALID    = 4001,
    AI_ERR_LICENSE_EXPIRED    = 4002,
    AI_ERR_LICENSE_MISMATCH   = 4003,
    AI_ERR_CAP_NOT_LICENSED   = 4004,
    AI_ERR_INTERNAL           = 5001,
} AiErrorCode;

#ifdef __cplusplus
}
#endif

#endif /* AGILESTAR_AI_TYPES_H */
```

---

## 4. 统一能力接口

### 4.1 ai_capability.h

```c
#ifndef AGILESTAR_AI_CAPABILITY_H
#define AGILESTAR_AI_CAPABILITY_H

#include "ai_types.h"

#ifdef _WIN32
  #define AI_EXPORT __declspec(dllexport)
#else
  #define AI_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/**
 * 创建能力实例。
 *
 * @param model_dir  模型包目录的绝对路径，包含 manifest.json 和 model.onnx
 * @param config_json  可选的 JSON 配置字符串（推理参数覆盖），可传 NULL 使用 manifest 默认值
 * @return 实例 Handle，失败返回 NULL
 */
AI_EXPORT AiHandle AiCreate(const char* model_dir, const char* config_json);

/**
 * 初始化实例（加载模型、校验 License、预热推理引擎）。
 * 必须在 AiCreate 后、AiInfer 前调用。
 *
 * @return AI_OK 成功，其他值见 AiErrorCode
 */
AI_EXPORT int32_t AiInit(AiHandle handle);

/**
 * 执行单次推理。
 * 线程安全约束：同一 handle 不得并发调用，不同 handle 之间线程安全。
 *
 * @param handle  由 AiCreate 返回的实例 Handle
 * @param input   输入图像，调用方持有内存
 * @param output  推理结果，由插件分配内存，调用方通过 AiFreeResult 释放
 * @return AI_OK 成功，其他值见 AiErrorCode
 */
AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output);

/**
 * 热重载模型（替换模型文件后，无需销毁重建实例）。
 * 重载期间此 handle 不可用，调用方应在 reload 完成后再使用。
 *
 * @param new_model_dir  新模型包目录的绝对路径
 * @return AI_OK 成功，其他值见 AiErrorCode
 */
AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir);

/**
 * 获取能力和模型信息（JSON 字符串）。
 *
 * 与 snprintf 行为一致：
 *   - 成功时返回实际写入字节数（不含 '\0'）
 *   - buf_len 不足时返回所需缓冲区大小（正整数，不含 '\0'），调用方可据此分配更大缓冲区再次调用
 *   - handle 无效或其他错误时返回负数（对应 AiErrorCode 取负，如 -5001）
 *
 * @param handle    实例 Handle
 * @param info_buf  调用方分配的缓冲区，可传 NULL 配合 buf_len=0 查询所需大小
 * @param buf_len   缓冲区长度（字节），传 0 时仅返回所需大小
 * @return 见上述说明
 */
AI_EXPORT int32_t AiGetInfo(AiHandle handle, char* info_buf, int32_t buf_len);

/**
 * 销毁实例，释放所有资源。
 * 调用后 handle 不得再使用。
 */
AI_EXPORT void AiDestroy(AiHandle handle);

/**
 * 释放由 AiInfer 分配的结果内存。
 * 必须由与 AiInfer 相同的插件调用（不得跨模块 free）。
 */
AI_EXPORT void AiFreeResult(AiResult* result);

/**
 * 获取插件 ABI 版本号（用于兼容性检查）。
 * 格式：major * 10000 + minor * 100 + patch
 */
AI_EXPORT int32_t AiGetAbiVersion(void);

#define AI_ABI_VERSION 10000  /* v1.0.0 */

#ifdef __cplusplus
}
#endif

#endif /* AGILESTAR_AI_CAPABILITY_H */
```

---

## 5. Runtime 管理接口

### 5.1 ai_runtime.h

```c
#ifndef AGILESTAR_AI_RUNTIME_H
#define AGILESTAR_AI_RUNTIME_H

#include "ai_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Runtime 初始化（进程级，调用一次）。
 * 扫描 so_dir 下所有能力 SO，扫描 model_base_dir 下模型包，
 * 加载 license_path 授权文件。
 */
int32_t AiRuntimeInit(const char* so_dir,
                      const char* model_base_dir,
                      const char* license_path);

/**
 * 获取已加载的能力列表（JSON 字符串）。
 */
int32_t AiRuntimeGetCapabilities(char* buf, int32_t buf_len);

/**
 * 从指定能力的实例池中获取一个可用实例。
 * 若池已满则阻塞等待，超时返回 NULL。
 *
 * @param capability_name  能力标识（如 "face_detect"）
 * @param timeout_ms       等待超时毫秒数，0 表示不等待
 */
AiHandle AiRuntimeAcquire(const char* capability_name, int32_t timeout_ms);

/**
 * 归还实例到实例池。
 */
void AiRuntimeRelease(AiHandle handle);

/**
 * 热重载指定能力（触发后台 reload 流程）。
 */
int32_t AiRuntimeReload(const char* capability_name);

/**
 * 获取 License 状态（JSON 字符串）。
 */
int32_t AiRuntimeGetLicenseStatus(char* buf, int32_t buf_len);

/**
 * Runtime 销毁（进程退出前调用）。
 */
void AiRuntimeDestroy(void);

#ifdef __cplusplus
}
#endif

#endif /* AGILESTAR_AI_RUNTIME_H */
```

---

## 6. JNI 接口层

JNI 接口层封装上述 C ABI，供 Java 调用。对应的 Java 包名为 `cn.agilestar.ai`。

### Java 调用示例

```java
import cn.agilestar.ai.AiCapability;
import cn.agilestar.ai.AiResult;

// 初始化
AiCapability cap = new AiCapability("face_detect", "/opt/ai/models/face_detect/current");
cap.init();

// 推理
byte[] imageData = Files.readAllBytes(Paths.get("test.jpg"));
AiResult result = cap.infer(imageData, width, height, channels);
System.out.println(result.getJsonResult());

// 释放
cap.destroy();
```

### JNI 原生接口声明（cn_agilestar_ai_AiCapability.h 节选）

```c
JNIEXPORT jlong   JNICALL Java_cn_agilestar_ai_AiCapability_nativeCreate(
    JNIEnv*, jobject, jstring modelDir, jstring configJson);

JNIEXPORT jint    JNICALL Java_cn_agilestar_ai_AiCapability_nativeInit(
    JNIEnv*, jobject, jlong handle);

JNIEXPORT jstring JNICALL Java_cn_agilestar_ai_AiCapability_nativeInfer(
    JNIEnv*, jobject, jlong handle,
    jbyteArray imageData, jint width, jint height, jint channels);

JNIEXPORT void    JNICALL Java_cn_agilestar_ai_AiCapability_nativeDestroy(
    JNIEnv*, jobject, jlong handle);
```

---

## 7. ABI 版本兼容性规则

| 变更类型 | 处理方式 |
|---------|---------|
| 新增接口（不破坏现有接口） | 次版本号 +1（向后兼容） |
| 修改现有接口签名 | 主版本号 +1，Runtime 做版本检查 |
| 修改数据结构布局 | 主版本号 +1，不可向后兼容 |
| 新增 error_code 值 | 次版本号 +1（调用方需处理未知 error_code） |

Runtime 在加载 SO 时调用 `AiGetAbiVersion()` 检查版本兼容性，版本不匹配则拒绝加载并记录错误。

---

## 8. 推理结果 JSON 格式

### 目标检测

```json
{
  "detections": [
    {
      "label": "face",
      "label_id": 0,
      "confidence": 0.95,
      "bbox": { "x1": 100, "y1": 80, "x2": 300, "y2": 320 }
    }
  ],
  "inference_time_ms": 12.5
}
```

### 二分类 / 多分类

```json
{
  "classifications": [
    { "label": "real", "label_id": 0, "confidence": 0.98 },
    { "label": "fake", "label_id": 1, "confidence": 0.02 }
  ],
  "top1_label": "real",
  "inference_time_ms": 5.2
}
```

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
