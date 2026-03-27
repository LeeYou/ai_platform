# 系统整体架构设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-27**

---

## 1. 平台定位

`ai_platform` 是一个 **AI 综合能力平台**，覆盖 AI 能力从数据集准备、模型训练、推理测试、C++ SO 编译，到生产镜像交付与授权管理的全生命周期流程。

核心设计原则：

- **能力插件化**：每个 AI 能力独立成一个 SO 插件，能力间完全隔离，支持独立更新与故障隔离。
- **挂载优先于内置**：生产镜像开箱即用，同时支持宿主机挂载目录覆盖内置资源（模型、SO、License），无需重新打包镜像即可完成现场更新。
- **双层 License 校验**：HTTP 服务层做路由级权限控制，SO 插件层做能力级签名验证，防止绕过。
- **实例池并发**：生产级并发设计，每个推理实例持有独立 CUDA 资源和缓冲区，不使用全局锁。
- **统一 C ABI**：跨平台、跨语言（Java JNI、Python ctypes）调用的基础，接口稳定性优先。

---

## 2. 子系统构成

```
┌──────────────────────────────────────────────────────────────────────┐
│                      AI 综合能力平台 (ai_platform)                    │
│                   北京爱知之星科技股份有限公司 agilestar.cn            │
├─────────────┬─────────────┬──────────────┬──────────────┬────────────┤
│  训练子系统  │  测试子系统  │  编译子系统   │  生产交付子系统│  授权子系统 │
│ (Train Svc) │ (Test Svc)  │ (Build Svc)  │ (Prod Svc)   │(License Svc│
├─────────────┴─────────────┴──────────────┴──────────────┴────────────┤
│                         公共基础设施层                                 │
│       数据集仓库 / 模型仓库 / 编译产物仓库 / 授权文件仓库 / 日志系统     │
├──────────────────────────────────────────────────────────────────────┤
│                       宿主机统一存储目录                               │
│   /data/ai_platform/{datasets, models, libs, licenses, logs, output} │
└──────────────────────────────────────────────────────────────────────┘
```

| 子系统 | Docker 镜像 | 职责 |
|--------|------------|------|
| 训练子系统 | `agilestar/ai-train:latest` | 数据集管理、模型训练、模型包导出 |
| 测试子系统 | `agilestar/ai-test:latest` | 模型推理测试、精度评估 |
| 编译子系统 | `agilestar/ai-builder-*:latest` | C++ SO/DLL 多平台编译 |
| 生产交付子系统 | `agilestar/ai-prod:latest` | 对外 REST HTTP 推理服务 |
| 授权子系统 | `agilestar/ai-license-mgr:latest` | License 生成、管理、校验 |

---

## 3. 生产容器内部 4 层结构

```
┌──────────────────────────────────────────────────────┐
│  Layer 1: HTTP 服务层                                  │
│  接收外部请求 / 参数校验 / License 状态检查 /           │
│  能力路由 / 日志 / 健康检查 / 管理接口                  │
├──────────────────────────────────────────────────────┤
│  Layer 2: Runtime 层                                  │
│  动态加载能力 SO / 管理实例池 / 并发调度 /              │
│  统一错误码 / reload / rollback                        │
├──────────────────────────────────────────────────────┤
│  Layer 3: Capability 插件层                           │
│  libface_detect.so / libhandwriting_reco.so /         │
│  librecapture_detect.so / lib<capability>.so          │
│  （每个 AI 能力独立一个 SO）                            │
├──────────────────────────────────────────────────────┤
│  Layer 4: 模型包层                                    │
│  model.onnx / manifest.json /                        │
│  preprocess.json / labels.json / checksum             │
└──────────────────────────────────────────────────────┘
```

---

## 4. 宿主机统一目录规范

所有数据通过宿主机统一目录在各容器间共享，挂载方式见各子系统文档。

```
/data/ai_platform/
├── datasets/                         # 训练数据集（宿主机只读挂载到训练容器）
│   ├── face_detect/
│   ├── handwriting_reco/
│   ├── recapture_detect/
│   └── <capability_name>/
│
├── models/                           # 标准模型包（训练容器写入，其余只读）
│   ├── face_detect/
│   │   ├── v1.0.0/
│   │   │   ├── model.onnx
│   │   │   ├── manifest.json
│   │   │   ├── preprocess.json
│   │   │   └── labels.json
│   │   └── current -> v1.0.0         # 符号链接，指向当前版本
│   └── <capability_name>/
│
├── libs/                             # 编译产物 SO/DLL（编译容器写入，生产只读）
│   ├── linux_x86_64/
│   │   └── face_detect/
│   │       ├── v1.0.0/
│   │       │   └── libface_detect.so
│   │       └── current -> v1.0.0
│   ├── linux_aarch64/
│   └── windows_x86_64/
│       └── face_detect/
│           └── v1.0.0/
│               └── face_detect.dll
│
├── licenses/                         # 授权文件（授权系统生成，生产容器只读）
│   └── <customer_id>/
│       └── license.bin
│
├── output/                           # 最终交付产物归档
│   └── <version>/
│
└── logs/                             # 各容器日志落地目录
    ├── train/
    ├── test/
    ├── build/
    └── prod/
```

---

## 5. 容器挂载策略汇总

| 容器 | 挂载源（宿主机） | 挂载目标（容器内） | 读写 |
|------|----------------|-----------------|------|
| 训练容器 | `/data/ai_platform/datasets/` | `/workspace/datasets` | 只读 |
| 训练容器 | `/data/ai_platform/models/` | `/workspace/models` | 读写 |
| 训练容器 | `/data/ai_platform/logs/train/` | `/workspace/logs` | 读写 |
| 测试容器 | `/data/ai_platform/models/` | `/workspace/models` | 只读 |
| 测试容器 | `/data/ai_platform/datasets/` | `/workspace/datasets` | 只读 |
| 编译容器 | 源码目录 | `/workspace/src` | 只读 |
| 编译容器 | `/data/ai_platform/libs/` | `/workspace/output` | 读写 |
| 生产容器 | `/data/ai_platform/models/` | `/mnt/ai_platform/models` | 只读 |
| 生产容器 | `/data/ai_platform/libs/` | `/mnt/ai_platform/libs` | 只读 |
| 生产容器 | `/data/ai_platform/licenses/` | `/mnt/ai_platform/licenses` | 只读 |
| 生产容器 | `/data/ai_platform/logs/prod/` | `/mnt/ai_platform/logs` | 读写 |

---

## 6. 资源加载优先级（生产容器）

```
1. 优先读取宿主机挂载目录 /mnt/ai_platform/<type>/<capability>/current/
2. 如缺失，回退读取镜像内置目录 /app/<type>/<capability>/current/
3. 二者均缺失 → 该能力不可用（健康检查返回 WARNING，推理接口返回 503）
```

这一策略保证：

- 镜像开箱即用（内置默认版本）
- 更新不必重打镜像（宿主机挂载覆盖）
- 支持快速回滚（切换 `current` 符号链接）
- 适合现场交付与维护

---

## 7. 新增 AI 能力流程

```
1. 在 /data/ai_platform/datasets/<new_capability>/ 下准备数据集
2. 在 cpp/capabilities/<new_capability>/ 下新建 CMake 插件工程（复用模板）
3. 在 train/scripts/<new_capability>/ 下新建训练脚本
4. 在训练 Web 页面配置新能力并开始训练
5. 训练完成，模型包导出到 /data/ai_platform/models/<new_capability>/v1.0.0/
6. 编译容器编译生成 lib<new_capability>.so
7. 测试容器验证推理结果
8. 授权系统为新能力颁发 License
9. 将新 SO 和模型包纳入生产镜像，或通过挂载目录热更新
```

---

## 8. 多平台交付矩阵

| 交付形式 | 平台 | 架构 | 接口 | 说明 |
|----------|------|------|------|------|
| Docker 镜像 | Linux | x86_64 / aarch64 | REST HTTP | GPU 优先，CPU 回退 |
| 单机 SO 包 | Linux | x86_64 / aarch64 | JNI (Java) | 含 JNI 桥接层 |
| DLL 包 | Windows | x86_64 | JNI / 原生 C | MSVC 编译，64 位 |
| DLL 包 | Windows | x86_32 | JNI / 原生 C | MSVC 编译，32 位 |

---

## 9. 技术选型

| 组件 | 技术 | 版本要求 |
|------|------|---------|
| 训练框架 | PyTorch | ≥2.0 |
| 训练框架 | PaddlePaddle | ≥2.5（可选） |
| 推理框架 | ONNXRuntime | ≥1.16 |
| 推理框架 | TensorRT | ≥8.6（GPU 加速） |
| C++ HTTP 服务 | Crow / cpp-httplib | 轻量，嵌入式友好 |
| 管理面 HTTP 服务 | Python FastAPI | ≥0.100 |
| 前端框架 | Vue3 + Element Plus | ≥3.3 |
| 容器编排 | Docker Compose | ≥2.20 |
| 多架构构建 | docker buildx | QEMU 模拟或原生构建 |
| 授权签名 | RSA-2048 + SHA256 | OpenSSL ≥3.0 |
| 模型格式 | ONNX | opset ≥14 |
| C++ 构建 | CMake | ≥3.26 |
| C++ 编译器（Linux） | GCC | ≥12 |
| C++ 编译器（Windows） | MSVC | ≥2022 |
| 源码编码 | UTF-8 | 全平台统一 |
| 基础训练镜像 | nvidia/cuda | 12.x-cudnn8-devel-ubuntu22.04 |

---

## 10. 关键设计决策

| 决策 | 原因 |
|------|------|
| 每个能力独立 SO | 能力隔离、更新粒度独立、故障定位简单、安全控制更精细 |
| 实例池而非全局锁 | 生产级并发需要，每个实例持有独立 CUDA 资源和缓冲区，避免串行瓶颈 |
| 挂载优先于内置 | 保证镜像开箱即用，现场更新免重打镜像，支持快速回滚 |
| 双层 License 校验 | HTTP 层做路由权限，SO 层做能力签名验证，防止绕过任一层 |
| 统一 C ABI | 跨平台、跨语言（Java JNI、Python ctypes）互操作的基础，接口稳定优先 |
| 模型包而非裸文件 | 带 manifest 和 checksum 的模型包，运行时加载前做完整校验，防版本混用 |
| UTF-8 统一编码 | 避免多平台中文乱码，所有源码、文档、配置文件统一 UTF-8 |

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
