# C++ 编码规范

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-27**  
**基础规范：Google C++ Style Guide（含公司定制规则）**

---

## 1. 总则

本规范基于 [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html)，并针对本项目实际情况做出若干定制。所有 C++ 源码必须遵守本规范。

- 所有源码文件统一使用 **UTF-8** 编码（无 BOM）
- 行尾换行统一使用 **LF**（Unix 风格）
- 缩进使用 **2 个空格**，不使用 Tab
- 每行最大宽度 **100 个字符**

---

## 2. 命名规范

### 2.1 总体规则

| 类别 | 命名风格 | 示例 |
|------|---------|------|
| 类名、结构体名 | `UpperCamelCase` | `FaceDetector`, `ModelManifest` |
| 函数名（成员 & 非成员） | `UpperCamelCase` | `LoadModel()`, `GetCapabilityName()` |
| 变量名（局部、参数） | `lower_snake_case` | `model_path`, `input_image` |
| 成员变量 | `lower_snake_case`（**无下划线后缀**） | `model_dir`, `instance_count` |
| 常量（constexpr / const） | `kUpperCamelCase` | `kMaxInstances`, `kDefaultThreshold` |
| 枚举值 | `kUpperCamelCase` | `kErrorCodeOk`, `kColorFormatBgr` |
| 宏 | `UPPER_SNAKE_CASE` | `AI_EXPORT`, `AI_ABI_VERSION` |
| 命名空间 | `lower_snake_case` | `agilestar::ai`, `agilestar::runtime` |
| 文件名 | `lower_snake_case` | `face_detector.cpp`, `model_loader.h` |
| 接口（纯虚类） | `I` 前缀 + `UpperCamelCase` | `ICapability`, `IModelLoader` |

### 2.2 公司定制规则：成员变量命名

> **【强制】成员变量统一使用 `lower_snake_case`，不使用 Google 原版建议的后缀下划线（`name_`）。**

```cpp
// 正确 ✓
class FaceDetector {
 private:
  std::string model_dir;
  int instance_count;
  float threshold;
};

// 错误 ✗ （禁止使用后缀下划线）
class FaceDetector {
 private:
  std::string model_dir_;   // 禁止
  int instance_count_;      // 禁止
};
```

### 2.3 其他命名示例

```cpp
// 正确 ✓
namespace agilestar {
namespace ai {

constexpr int kMaxInstances = 8;
constexpr float kDefaultThreshold = 0.5f;

class InstancePool {
 public:
  bool Initialize(int min_count, int max_count);
  AiHandle Acquire(int timeout_ms);
  void Release(AiHandle handle);

 private:
  int min_count;
  int max_count;
  std::vector<AiHandle> available_handles;
  std::mutex pool_mutex;
};

}  // namespace ai
}  // namespace agilestar
```

---

## 3. 头文件规范

### 3.1 头文件保护

所有头文件使用 `#pragma once`（不使用传统 `#ifndef` 宏守卫）：

```cpp
#pragma once

#include "ai_types.h"
// ...
```

### 3.2 Include 顺序

按以下顺序排列 `#include`，各组之间空一行：

```cpp
// 1. 对应的 .h 文件（仅在 .cpp 中）
#include "face_detector.h"

// 2. C 系统头文件
#include <stdint.h>
#include <string.h>

// 3. C++ 标准库头文件
#include <memory>
#include <string>
#include <vector>

// 4. 第三方库头文件
#include <onnxruntime_cxx_api.h>

// 5. 本项目头文件
#include "sdk/ai_types.h"
#include "runtime/model_loader.h"
```

### 3.3 头文件依赖原则

- 禁止循环依赖
- 尽量使用前向声明，减少头文件包含
- 内联函数不应过长（超过 10 行不建议内联）

---

## 4. 类与面向对象

### 4.1 类定义顺序

```cpp
class FaceDetector {
 public:
  // 构造函数与析构函数
  explicit FaceDetector(const std::string& model_dir);
  ~FaceDetector();

  // 禁用拷贝（推理实例通常不可拷贝）
  FaceDetector(const FaceDetector&) = delete;
  FaceDetector& operator=(const FaceDetector&) = delete;

  // 公共接口
  bool Initialize();
  int32_t Infer(const AiImage& input, AiResult* output);

 private:
  // 私有方法
  bool LoadModel();
  void Preprocess(const AiImage& input, std::vector<float>* tensor);

  // 私有成员变量（lower_snake_case，无后缀下划线）
  std::string model_dir;
  std::unique_ptr<Ort::Session> ort_session;
  float threshold;
  bool initialized;
};
```

### 4.2 继承与接口

- 纯虚接口类使用 `I` 前缀
- 虚析构函数必须声明
- 覆盖虚函数必须使用 `override` 关键字

```cpp
class ICapability {
 public:
  virtual ~ICapability() = default;

  virtual bool Initialize(const std::string& model_dir) = 0;
  virtual int32_t Infer(const AiImage& input, AiResult* output) = 0;
  virtual std::string GetCapabilityName() const = 0;
};

class FaceDetector : public ICapability {
 public:
  bool Initialize(const std::string& model_dir) override;
  int32_t Infer(const AiImage& input, AiResult* output) override;
  std::string GetCapabilityName() const override;
};
```

---

## 5. 函数规范

### 5.1 参数传递约定

| 场景 | 约定 |
|------|------|
| 只读参数（基础类型） | 值传递 `int count` |
| 只读参数（对象/字符串） | `const T&` |
| 输出参数 | 指针 `T* output`（不用引用输出） |
| 输入输出参数 | 指针 `T* inout` |
| 转移所有权 | `std::unique_ptr<T>` 值传递 |

```cpp
// 正确 ✓
bool LoadModel(const std::string& model_path, ModelConfig* config);
std::unique_ptr<ICapability> CreateCapability(const std::string& name);

// 错误 ✗
bool LoadModel(std::string model_path, ModelConfig& config);  // 引用输出
```

### 5.2 函数长度

- 函数不宜超过 **50 行**（不含注释和空行）
- 超过 50 行的函数应拆分为多个子函数

---

## 6. 内存管理

### 6.1 智能指针优先

```cpp
// 正确 ✓ 独占所有权
std::unique_ptr<FaceDetector> detector =
    std::make_unique<FaceDetector>(model_dir);

// 正确 ✓ 共享所有权
std::shared_ptr<ModelManifest> manifest =
    std::make_shared<ModelManifest>();
```

### 6.2 C ABI 内存约定

C ABI 接口层（SO 导出函数）遵循以下内存规则：

- **输入内存**：由调用方持有，插件不得持有超过函数调用期的引用
- **输出内存（AiResult）**：由插件分配，调用方必须通过 `AiFreeResult()` 释放
- **绝不**返回内部临时缓冲区的指针

```cpp
// 正确 ✓ 插件分配输出内存
int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
  std::string json = RunInference(*input);
  output->json_result = new char[json.size() + 1];
  std::memcpy(output->json_result, json.c_str(), json.size() + 1);
  output->result_len = static_cast<int32_t>(json.size());
  output->error_code = AI_OK;
  output->error_msg = nullptr;
  return AI_OK;
}

void AiFreeResult(AiResult* result) {
  if (result) {
    delete[] result->json_result;
    delete[] result->error_msg;
    result->json_result = nullptr;
    result->error_msg = nullptr;
  }
}
```

---

## 7. 线程安全

### 7.1 基本原则

- 共享状态的读写必须有互斥保护（`std::mutex` 或 `std::shared_mutex`）
- 推理实例持有独立上下文，不共享临时缓冲区
- 全局静态状态（可变）禁止存在于能力插件中
- 所有线程安全约束**必须**以注释明确说明

```cpp
class InstancePool {
 public:
  // 线程安全：此函数可被多线程并发调用
  AiHandle Acquire(int timeout_ms);

  // 线程安全：此函数可被多线程并发调用
  void Release(AiHandle handle);

 private:
  // 以下成员需持有 pool_mutex 才可访问
  std::mutex pool_mutex;
  std::condition_variable pool_cv;
  std::vector<AiHandle> available_handles;
};
```

---

## 8. 错误处理

### 8.1 C++ 层

- 内部 C++ 代码可使用异常，但**禁止**异常穿透 C ABI 边界
- C ABI 导出函数必须捕获所有异常，转换为错误码返回

```cpp
// ABI 导出函数必须捕获所有异常
int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
  try {
    auto* detector = static_cast<FaceDetector*>(handle);
    return detector->Infer(*input, output);
  } catch (const std::exception& e) {
    output->error_code = AI_ERR_INTERNAL;
    // 安全设置 error_msg
    const std::string msg = e.what();
    output->error_msg = new char[msg.size() + 1];
    std::memcpy(output->error_msg, msg.c_str(), msg.size() + 1);
    return AI_ERR_INTERNAL;
  } catch (...) {
    output->error_code = AI_ERR_INTERNAL;
    return AI_ERR_INTERNAL;
  }
}
```

---

## 9. 注释规范

### 9.1 文件头注释

每个头文件和源文件开头必须包含版权声明：

```cpp
// Copyright 2026 北京爱知之星科技股份有限公司 (Agile Star)
// SPDX-License-Identifier: Proprietary
//
// 文件描述：人脸检测能力插件实现
```

### 9.2 公共接口注释（Doxygen）

```cpp
/**
 * @brief 执行单次推理。
 *
 * 线程安全约束：同一 handle 不得并发调用，不同 handle 之间线程安全。
 *
 * @param handle  由 AiCreate 返回的实例 Handle
 * @param input   输入图像，调用方持有内存，函数返回后可安全释放
 * @param output  推理结果，由插件分配内存，调用方通过 AiFreeResult 释放
 * @return AI_OK 成功，其他值见 AiErrorCode
 */
AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output);
```

### 9.3 实现注释

- 解释"为什么"而不是"做什么"
- 复杂算法必须有注释
- 避免无意义的重复注释

---

## 10. 格式化工具

使用 `clang-format` 自动格式化，项目根目录提供 `.clang-format` 配置文件：

```yaml
# .clang-format
BasedOnStyle: Google
IndentWidth: 2
ColumnLimit: 100
# 成员变量对齐
AlignConsecutiveDeclarations: false
# 函数参数换行
AllowShortFunctionsOnASingleLine: Inline
```

提交前运行：

```bash
clang-format -i --style=file path/to/file.cpp
```

---

## 11. 静态分析

推荐使用以下工具做静态分析（CI 流水线集成）：

| 工具 | 用途 |
|------|------|
| `clang-tidy` | 代码规范检查、潜在 bug 检测 |
| `cppcheck` | 静态缺陷检测 |
| `AddressSanitizer` | 运行时内存错误检测 |
| `ThreadSanitizer` | 运行时数据竞争检测 |

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
