# 生产交付子系统设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-27**

---

## 1. 概述

生产交付子系统提供面向最终客户的 AI 推理服务，以 Docker 镜像形式交付。镜像内置默认版本的 SO 和模型包（开箱即用），同时支持通过宿主机挂载目录覆盖内置资源，实现现场热更新。

---

## 2. 容器设计

| 属性 | 值 |
|------|-----|
| 镜像名 | `agilestar/ai-prod:latest` |
| 基础镜像 | `ubuntu:22.04`（含 ONNXRuntime，TensorRT 可选） |
| 服务端口 | 8080（REST HTTP API） |
| 主服务 | Python FastAPI（HTTP 层）+ C Runtime（推理层） |
| GPU 策略 | 启动时检测 CUDA 可用性，自动选择 GPU/CPU 后端 |

### 挂载目录（宿主机可覆盖内置）

| 宿主机路径 | 容器路径 | 模式 | 说明 |
|-----------|---------|------|------|
| `/data/ai_platform/models/` | `/mnt/ai_platform/models` | 只读 | 覆盖镜像内 `/app/models/` |
| `/data/ai_platform/libs/<arch>/` | `/mnt/ai_platform/libs` | 只读 | 覆盖镜像内 `/app/libs/` |
| `/data/ai_platform/licenses/` | `/mnt/ai_platform/licenses` | 只读 | 覆盖镜像内 `/app/licenses/` |
| `/data/ai_platform/logs/prod/` | `/mnt/ai_platform/logs` | 读写 | 日志落地 |

---

## 3. 容器内部 4 层架构

### Layer 1：HTTP 服务层

职责：接收外部 HTTP 请求 → 参数校验 → 路由到 Runtime 层 → 透传 Runtime 错误 → 返回统一 JSON 响应

技术：Python FastAPI（快速开发、Swagger 自动生成）

### Layer 2：Runtime 层

职责：动态加载能力 SO → 管理推理实例池 → 并发调度 → 统一错误码 → 热重载 / 回滚

技术：Python ctypes 调用 C Runtime 库（`libai_runtime.so`）

### Layer 3：Capability 插件层

每个 AI 能力独立一个 SO，运行时由 Runtime 层通过 `dlopen` 动态加载。

```
/app/libs/
├── libface_detect.so
├── libhandwriting_reco.so
├── librecapture_detect.so
└── lib<capability>.so
```

### Layer 4：模型包层

```
/app/models/
├── face_detect/
│   └── current/                # 符号链接指向当前版本目录
│       ├── model.onnx
│       ├── manifest.json
│       ├── preprocess.json
│       └── labels.json
└── <capability>/
```

---

## 4. 资源加载优先级

```python
def resolve_resource_path(capability: str, resource_type: str) -> str:
    """
    resource_type: "models" | "libs"
    优先级: 宿主机挂载 > 镜像内置
    """
    mount_path = f"/mnt/ai_platform/{resource_type}/{capability}/current"
    builtin_path = f"/app/{resource_type}/{capability}/current"

    if os.path.exists(mount_path):
        return mount_path   # 宿主机挂载版本优先
    elif os.path.exists(builtin_path):
        return builtin_path  # 回退到镜像内置版本
    else:
        raise CapabilityNotAvailableError(capability)
```

---

## 5. REST API 规范

### 5.1 接口列表

| 接口 | 方法 | 说明 | 鉴权 |
|------|------|------|------|
| `/api/v1/health` | GET | 服务健康状态、各能力加载状态 | 无 |
| `/api/v1/capabilities` | GET | 已加载能力列表及版本信息 | 无 |
| `/api/v1/infer/{capability}` | POST | 推理接口（License 由 SO 层执行） | SO License |
| `/api/v1/license/status` | GET | 授权状态、有效期、覆盖能力列表 | 无 |
| `/api/v1/admin/reload` | POST | 热重载模型/SO | Admin Token |
| `/api/v1/admin/reload/{capability}` | POST | 热重载指定能力 | Admin Token |
| `/api/v1/docs` | GET | Swagger API 文档（自动生成） | 无 |

### 5.2 推理接口详述

**请求**

```
POST /api/v1/infer/face_detect
Content-Type: multipart/form-data

image: <binary image file>
options: {"threshold": 0.5}   # 可选 JSON 参数
```

**响应（成功）**

```json
{
  "code": 0,
  "message": "success",
  "capability": "face_detect",
  "model_version": "1.0.0",
  "inference_time_ms": 12.5,
  "result": {
    "detections": [
      {
        "label": "face",
        "confidence": 0.95,
        "bbox": { "x1": 100, "y1": 80, "x2": 300, "y2": 320 }
      }
    ]
  }
}
```

**响应（错误）**

```json
{
  "code": 4001,
  "message": "License expired",
  "capability": "face_detect"
}
```

### 5.3 健康检查响应

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "company": "agilestar.cn",
  "capabilities": {
    "face_detect": { "status": "loaded", "model_version": "1.0.0", "source": "mount" },
    "handwriting_reco": { "status": "loaded", "model_version": "1.0.0", "source": "builtin" },
    "recapture_detect": { "status": "unavailable", "reason": "model_not_found" }
  },
  "license": {
    "status": "valid",
    "valid_until": "2026-10-01T00:00:00Z",
    "days_remaining": 187
  },
  "gpu_available": true,
  "backend": "onnxruntime-gpu"
}
```

---

## 6. 推理实例池设计

为支持生产级并发请求，每个能力维护一个推理实例池，每个实例持有独立上下文。

```
请求到达
  → 调用 Runtime Acquire（由 SO 层执行 License 校验）
  → 从对应能力的实例池获取可用实例
    （若池已满 → 等待，超时返回 503）
  → 执行 AiInfer()
    （独立 CUDA stream / 独立缓冲区）
  → 归还实例到池
  → 返回推理结果
```

### 实例池参数配置

```yaml
# 生产容器配置文件 config.yaml

instance_pool:
  default_min_instances: 1
  default_max_instances: 4         # 可由环境变量覆盖
  acquire_timeout_seconds: 30
  gpu_memory_per_instance_mb: 512  # 用于计算 max_instances 上限

capabilities:
  face_detect:
    min_instances: 2
    max_instances: 8
  handwriting_reco:
    min_instances: 1
    max_instances: 4
```

### 并发安全约束

- 不依赖可变全局静态状态
- 不共享临时缓冲区
- 不返回内部临时内存指针（调用方通过 `AiFreeResult` 释放结果）
- 初始化与销毁过程线程安全
- Reload 行为与推理行为隔离（reload 期间旧实例继续服务直到全部归还）

---

## 7. 热重载与回滚机制

### 更新三类资源

| 资源类型 | 更新目录 | 触发方式 |
|---------|---------|---------|
| License | `/mnt/ai_platform/licenses/` | 自动检测（60 秒轮询）或 `/api/v1/admin/reload` |
| 模型包 | `/mnt/ai_platform/models/<capability>/` | `POST /api/v1/admin/reload/{capability}` |
| SO 插件 | `/mnt/ai_platform/libs/<capability>/` | `POST /api/v1/admin/reload/{capability}` |

### 更新流程

```
1. 新版本文件放入 <type>/<capability>/v2.0.0/
2. 更新 <type>/<capability>/current -> v2.0.0 符号链接
3. 调用 POST /api/v1/admin/reload/{capability}
4. Runtime 验证 manifest / checksum / license 兼容性
5. 验证失败 → current 回退到旧版本 → 旧实例继续服务
6. 验证成功 → 预热新实例 → 新实例加入池
7. 等待旧实例全部归还 → 销毁旧实例
```

---

## 8. GPU/CPU 自动选择

启动脚本 `docker-entrypoint.sh` 逻辑：

```bash
#!/bin/bash
if nvidia-smi > /dev/null 2>&1; then
    echo "[ai-prod] GPU detected, using ONNXRuntime CUDA/TensorRT backend"
    export AI_BACKEND=onnxruntime-gpu
else
    echo "[ai-prod] No GPU detected, falling back to CPU backend"
    export AI_BACKEND=onnxruntime-cpu
fi
exec python /app/web_service/main.py
```

---

## 9. 交付物清单

每次正式生产交付包含以下内容：

```
delivery_package/
├── docker/
│   ├── agilestar-ai-prod-linux-x86_64-v1.0.0.tar.gz
│   └── agilestar-ai-prod-linux-aarch64-v1.0.0.tar.gz
├── sdk_linux_x86_64/
│   ├── lib/libface_detect.so
│   ├── include/ai_capability.h
│   └── models/face_detect/
├── sdk_linux_aarch64/
├── sdk_windows_x86_64/
│   └── lib/face_detect.dll
├── sdk_windows_x86/
│   └── lib/face_detect.dll  (32 位)
├── licenses/
│   └── license.bin
├── mount_template/           # 宿主机挂载目录模板及说明
├── docs/
│   ├── API文档.md
│   ├── 部署手册.md
│   ├── 更新手册.md
│   └── 验收手册.md
└── tools/
    └── license_tool          # 授权查询命令行工具
```

---

## 10. 统一错误码表

> **分层说明**：1xxx/2xxx/4xxx/5xxx 错误码同时适用于 HTTP JSON 响应和 C ABI 返回值（见 `ai_types.h` 的 `AiErrorCode`）；**3xxx 错误码仅用于 HTTP 服务层**，不在 C ABI 中定义（实例池由 Runtime 层管理，SO 插件不感知并发调度）。

| 错误码 | 含义 | 层级 |
|-------|------|------|
| 0 | 成功 | 所有层 |
| 1001 | 参数无效 | HTTP + C ABI |
| 1002 | 图片解码失败 | HTTP + C ABI |
| 2001 | 能力不存在 | HTTP + C ABI |
| 2002 | 能力加载失败 | HTTP + C ABI |
| 2003 | 模型文件损坏（checksum 不匹配） | HTTP + C ABI |
| 2004 | 推理执行错误 | HTTP + C ABI |
| 3001 | 实例池已满，请求超时 | **HTTP 服务层专属** |
| 4001 | License 无效 | HTTP + C ABI |
| 4002 | License 已过期 | HTTP + C ABI |
| 4003 | 机器指纹不匹配 | HTTP + C ABI |
| 4004 | 能力未授权 | HTTP + C ABI |
| 5001 | 内部错误 | 所有层 |

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
