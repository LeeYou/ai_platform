# AI综合能力平台 (ai_platform)

**北京爱知之星科技股份有限公司 (Agile Star)**  
**官网：[agilestar.cn](https://agilestar.cn)**

---

## 项目简介

`ai_platform` 是北京爱知之星科技股份有限公司自主研发的 **AI 综合能力平台**，覆盖 AI 能力从数据集准备、模型训练、推理测试、C++ SO 编译，到生产镜像交付与授权管理的全生命周期流程。

平台以模块化、插件化为核心设计理念，支持动态新增 AI 能力（人脸检测、手写签字识别、翻拍检测、证件分类识别等），并提供完善的多平台交付方案（Linux x86_64/aarch64、Windows x86/x86_64、Docker 镜像、JNI SO 包）。

---

## 平台全景架构

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

### 生产容器内部 4 层架构

```
┌──────────────────────────────────────────┐
│  Layer 1: HTTP 服务层                     │
│  REST API / 路由 / License 校验 / 日志    │
├──────────────────────────────────────────┤
│  Layer 2: Runtime 层                      │
│  能力插件加载 / 实例池 / 并发调度 / Reload │
├──────────────────────────────────────────┤
│  Layer 3: Capability 插件层               │
│  libface_detect.so  libhandwriting_reco.so│
├──────────────────────────────────────────┤
│  Layer 4: 模型包层                        │
│  model.onnx / manifest.json / 预处理配置  │
└──────────────────────────────────────────┘
```

---

## 工程目录结构

```
ai_platform/
├── docs/                           # 项目文档
│   ├── design/                     # 子系统设计文档
│   │   ├── architecture.md         # 系统整体架构
│   │   ├── train_service.md        # 训练子系统
│   │   ├── test_service.md         # 测试子系统
│   │   ├── build_service.md        # 编译子系统
│   │   ├── prod_service.md         # 生产交付子系统
│   │   ├── license_service.md      # 授权子系统
│   │   └── cpp_abi.md              # C++ ABI 接口规范
│   ├── cpp_coding_standard.md      # C++ 编码规范
│   └── development_plan.md         # 分阶段开发计划
├── train/                          # 训练子系统
│   ├── Dockerfile
│   ├── backend/                    # FastAPI 后端
│   ├── frontend/                   # Vue3 前端
│   └── scripts/                    # 各 AI 能力训练脚本
├── test/                           # 测试子系统
│   ├── Dockerfile
│   ├── backend/
│   └── frontend/
├── build/                          # 编译子系统
│   ├── Dockerfile.linux_x86
│   ├── Dockerfile.linux_arm
│   ├── Dockerfile.windows
│   └── scripts/
├── cpp/                            # C++ 推理代码
│   ├── CMakeLists.txt
│   ├── sdk/                        # 公共 SDK 头文件（统一 ABI）
│   ├── runtime/                    # 通用 Runtime 库
│   ├── capabilities/               # 各 AI 能力插件 SO
│   │   ├── face_detect/
│   │   ├── handwriting_reco/
│   │   └── recapture_detect/
│   └── jni/                        # JNI 接口层
├── prod/                           # 生产交付子系统
│   ├── Dockerfile
│   └── web_service/                # 主 HTTP 服务
├── license/                        # 授权管理子系统
│   ├── Dockerfile
│   ├── backend/
│   ├── frontend/
│   └── tools/
├── deploy/                         # 部署编排
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   └── mount_template/             # 宿主机目录模板
└── scripts/                        # 平台级脚本（构建/打包/交付）
```

---

## 宿主机统一目录规范

```
/data/ai_platform/
├── datasets/          # 训练数据集（只读挂载到训练容器）
│   ├── face_detect/
│   ├── handwriting_reco/
│   └── <capability>/
├── models/            # 标准模型包（训练输出，测试/生产使用）
│   └── <capability>/<version>/
├── libs/              # 编译产物 SO/DLL（编译输出，生产使用）
│   ├── linux_x86_64/<capability>/<version>/
│   ├── linux_aarch64/
│   └── windows_x86_64/
├── licenses/          # 授权文件
├── output/            # 最终交付产物归档
└── logs/              # 各容器日志落地
```

---

## 快速导航

| 文档 | 说明 |
|------|------|
| [系统整体架构](docs/design/architecture.md) | 架构总览、目录规范、技术选型 |
| [训练子系统](docs/design/train_service.md) | 训练容器、Web 页面、训练流程、模型包格式 |
| [测试子系统](docs/design/test_service.md) | 测试容器、Web 页面、批量测试、版本对比 |
| [编译子系统](docs/design/build_service.md) | CMake 工程结构、多平台 Builder 镜像 |
| [生产交付子系统](docs/design/prod_service.md) | REST API、实例池、挂载加载策略、热重载 |
| [授权子系统](docs/design/license_service.md) | License 格式、机器指纹、双层校验、管理 Web |
| [C++ ABI 接口规范](docs/design/cpp_abi.md) | 统一 C ABI、生命周期接口、错误码 |
| [C++ 编码规范](docs/cpp_coding_standard.md) | Google C++ 风格 + 公司定制规则 |
| **[CUDA 版本规范](docs/cuda_version_standard.md)** | **标准 CUDA 11.8、依赖兼容性、验证脚本** |
| [开发计划](docs/development_plan.md) | 7 个阶段、里程碑、交付物清单 |
| [AI 能力超市总览](docs/ai_capability_market_overview.md) | 整体架构图、流程图、105 种能力全景、业务场景 |
| [Docker 镜像与容器管理手册](docs/docker_operations_manual.md) | 6 种镜像构建、启停、日志、健康检查、故障排查 |

---

## 多平台交付矩阵

| 交付形式 | 平台 | 架构 | 接口 |
|----------|------|------|------|
| Docker 镜像 | Linux | x86_64 / aarch64 | REST HTTP |
| 单机 SO 包 | Linux | x86_64 / aarch64 | JNI (Java) |
| DLL 包 | Windows | x86_64 / x86_32 | JNI / 原生 C |

---

## 技术选型

| 组件 | 技术 |
|------|------|
| **CUDA 版本** | **CUDA 11.8.0（LTS 标准版本）** |
| 训练框架 | PyTorch 2.0-2.4、PaddlePaddle |
| 推理框架 | ONNXRuntime、TensorRT |
| C++ HTTP 服务 | Crow / cpp-httplib |
| 管理面 HTTP 服务 | Python FastAPI |
| 前端 | Vue3 + Element Plus |
| 容器编排 | Docker + docker-compose |
| 多架构构建 | docker buildx |
| 授权签名 | RSA-2048 + SHA256 |
| 模型格式 | ONNX |
| C++ 构建 | CMake 3.26+ |
| 源码编码 | UTF-8（全平台统一） |

---

## 版权

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). All rights reserved.  
[agilestar.cn](https://agilestar.cn)
