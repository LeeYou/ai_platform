# Docker 镜像与容器构建管理手册

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.2 | 2026-03-29**  
**适用范围：AI 综合能力平台 (ai_platform) 全部 Docker 镜像**

---

## 目录

1. [概述](#1-概述)
2. [环境准备](#2-环境准备)
3. [镜像总览](#3-镜像总览)
4. [宿主机目录初始化](#4-宿主机目录初始化)
5. [各镜像构建详解](#5-各镜像构建详解)
   - [5.1 授权管理镜像 (ai-license-mgr)](#51-授权管理镜像-ai-license-mgr)
   - [5.2 训练镜像 (ai-train)](#52-训练镜像-ai-train)
   - [5.3 训练开发镜像 (ai-train-dev)](#53-训练开发镜像-ai-train-dev)
   - [5.4 测试镜像 (ai-test)](#54-测试镜像-ai-test)
   - [5.5 编译镜像 (ai-builder-linux-x86)](#55-编译镜像-ai-builder-linux-x86)
   - [5.6 生产推理镜像 (ai-prod)](#56-生产推理镜像-ai-prod)
6. [开发环境启停管理 (docker-compose)](#6-开发环境启停管理-docker-compose)
7. [生产环境启停管理 (docker-compose.prod)](#7-生产环境启停管理-docker-composeprod)
8. [日志管理](#8-日志管理)
9. [健康检查](#9-健康检查)
10. [镜像推送与仓库管理](#10-镜像推送与仓库管理)
11. [交付包打包](#11-交付包打包)
12. [常用运维命令速查表](#12-常用运维命令速查表)
13. [新增 AI 能力模块完整操作流程](#13-新增-ai-能力模块完整操作流程)
14. [故障排查指南](#14-故障排查指南)
15. [附录：端口分配表](#15-附录端口分配表)
16. [附录：授权安全模型](#16-附录授权安全模型)

---

## 1. 概述

AI 综合能力平台包含 **6 种 Docker 镜像**，覆盖 AI 能力从训练、测试、编译到生产推理和授权管理的全生命周期。本手册提供每种镜像的完整操作指南，包括构建、启停、日志查看、健康检查和故障排查。

### 镜像与子系统对应关系

```
┌────────────────────────────────────────────────────────────────────┐
│                    AI 综合能力平台 Docker 镜像体系                    │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│  开发/研发侧  │  开发/研发侧  │  开发/研发侧  │      生产侧           │
│              │              │              │                       │
│ ai-train     │ ai-test      │ ai-builder   │  ai-prod              │
│ (训练)       │ (测试)        │ (编译)       │  (生产推理)            │
│ :8001        │ :8002        │ :8004        │  :8080                │
├──────────────┴──────────────┴──────────────┤                       │
│                                            │  ai-license-mgr       │
│  ai-train-dev  (本地开发轻量版, :8001)       │  (授权管理)            │
│                                            │  :8003                │
└────────────────────────────────────────────┴───────────────────────┘
```

---

## 2. 环境准备

### 2.1 基础环境要求

| 组件 | 最低版本 | 推荐版本 | 用途 |
|------|---------|---------|------|
| Docker Engine | 20.10+ | 24.0+ | 容器运行时 |
| Docker Compose | v2.0+ | v2.20+ | 服务编排 |
| NVIDIA Driver | 525+ | 535+ | GPU 推理（仅 GPU 服务器） |
| NVIDIA Container Toolkit | 1.13+ | 1.14+ | GPU 容器支持 |
| 磁盘空间 | 50 GB | 100 GB+ | 镜像 + 数据 + 模型 |
| 内存 | 8 GB | 32 GB+ | 训练/推理 |

### 2.2 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 重新登录使 docker 组生效

# 验证安装
docker --version
docker compose version
```

### 2.3 安装 NVIDIA Container Toolkit（仅 GPU 服务器）

```bash
# 添加 NVIDIA 仓库
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 安装
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 验证
docker run --rm --gpus all nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 nvidia-smi
```

### 2.4 CUDA 版本兼容性说明

本平台默认使用 **CUDA 11.8** 作为训练镜像的基础版本，同时支持 CUDA 12.1。

#### 已验证兼容的 NVIDIA CUDA 镜像

| 镜像 | CUDA 版本 | 用途 | 状态 |
|------|-----------|------|------|
| `nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04` | 11.8 | 训练（含编译工具链） | ✅ **默认推荐** |
| `nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04` | 11.8 | 推理运行时（轻量） | ✅ 支持 |
| `nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04` | 12.1 | 训练（可选） | ✅ 支持 |

#### 主要依赖库兼容性

| 依赖库 | CUDA 11.8 | CUDA 12.1 | 说明 |
|--------|-----------|-----------|------|
| PyTorch 2.0-2.4 | ✅ | ✅ | 官方同时提供 cu118 和 cu121 wheel |
| ONNXRuntime 1.18 | ✅ | ✅ | GPU 版支持 CUDA 11.8+ |
| TensorRT 8.6 | ✅ | ✅ | 支持 CUDA 11.8+ |
| cuDNN 8.x | ✅ | ✅ | 两个版本都已包含 |

#### 切换 CUDA 版本

```bash
# 使用默认 CUDA 11.8 构建训练镜像
docker build -t agilestar/ai-train:latest -f train/Dockerfile .

# 切换到 CUDA 12.1 构建训练镜像
docker build -t agilestar/ai-train:latest -f train/Dockerfile \
  --build-arg CUDA_BASE_IMAGE=nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04 .
```

> **NVIDIA 驱动兼容性**：CUDA 11.8 要求 NVIDIA 驱动 ≥ 520，CUDA 12.1 要求 ≥ 530。
> 如果宿主机驱动较旧，建议使用 CUDA 11.8。

### 2.5 配置 Docker 日志驱动（推荐）

编辑 `/etc/docker/daemon.json`：

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "5"
  },
  "default-address-pools": [
    {"base": "172.20.0.0/16", "size": 24}
  ]
}
```

```bash
sudo systemctl restart docker
```

---

## 3. 镜像总览

| 序号 | 镜像名 | Dockerfile 路径 | 基础镜像 | 端口 | 用途 |
|------|--------|----------------|---------|------|------|
| 1 | `agilestar/ai-license-mgr` | `license/backend/Dockerfile` | `python:3.11-slim` | 8003 | 授权管理 Web + API |
| 2 | `agilestar/ai-train` | `train/Dockerfile` | `nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04`（默认，支持切换为12.1） | 8001 | GPU 训练服务 |
| 3 | `agilestar/ai-train-dev` | `train/Dockerfile.dev` | `python:3.11-slim` | 8001 | 本地开发训练（无 GPU） |
| 4 | `agilestar/ai-test` | `test/Dockerfile` | `python:3.11-slim` | 8002 | 模型测试与精度评估 |
| 5 | `agilestar/ai-builder-linux-x86` | `build/Dockerfile.linux_x86` | `ubuntu:22.04` | 8004 | C++ 多平台编译 |
| 6 | `agilestar/ai-prod` | `prod/Dockerfile` | `ubuntu:22.04` | 8080 | 生产 AI 推理服务 |

---

## 4. 宿主机目录初始化

> ⚠️ **首次部署前必须执行**，所有容器依赖此目录结构。

### 4.1 使用初始化脚本（推荐）

```bash
# 使用默认路径 /data/ai_platform
sudo bash deploy/mount_template/init_host_dirs.sh

# 或指定自定义路径
AI_PLATFORM_ROOT=/custom/path sudo -E bash deploy/mount_template/init_host_dirs.sh
```

### 4.2 手动创建

```bash
export AI_ROOT=/data/ai_platform

sudo mkdir -p ${AI_ROOT}/{datasets,models,libs,licenses,output}
sudo mkdir -p ${AI_ROOT}/logs/{train,test,build,license,prod}
sudo mkdir -p ${AI_ROOT}/libs/{linux_x86_64,linux_aarch64,windows_x86_64}

# 设置权限
sudo chmod 700 ${AI_ROOT}/licenses           # 授权文件：仅 root 可读
sudo chmod -R a-w ${AI_ROOT}/datasets         # 数据集：只读（防止训练容器误写）
sudo chmod -R 777 ${AI_ROOT}/logs             # 日志目录：容器可写
```

### 4.3 最终目录结构

```
/data/ai_platform/
├── datasets/                   # 训练数据集（只读挂载到训练容器）
│   ├── face_detect/
│   ├── handwriting_reco/
│   ├── recapture_detect/
│   └── id_card_classify/
├── models/                     # 模型包（训练产出，测试/生产使用）
│   └── <capability>/<version>/
│       ├── model.onnx
│       └── manifest.json
├── libs/                       # 编译产物 SO/DLL
│   ├── linux_x86_64/<capability>/<version>/
│   ├── linux_aarch64/
│   └── windows_x86_64/
├── licenses/                   # 授权文件（RSA-2048 签名）
│   └── license.bin
├── logs/                       # 各容器日志
│   ├── train/
│   ├── test/
│   ├── build/
│   ├── license/
│   └── prod/
├── pipelines/                  # AI 编排 Pipeline 配置（JSON 文件）
└── output/                     # 交付产物归档
```

---

## 5. 各镜像构建详解

> 以下所有命令均在仓库根目录执行：`cd /path/to/ai_platform`

### 5.1 授权管理镜像 (ai-license-mgr)

**用途**：提供授权管理 Web UI 和 API，生成/管理/吊销 License 文件。

**Dockerfile 路径**：`license/backend/Dockerfile`

**基础镜像**：`python:3.11-slim`（两阶段构建：Node.js 编译前端 + Python 运行后端）

**暴露端口**：8003

#### 构建命令

```bash
# 标准构建
docker build -t agilestar/ai-license-mgr:latest -f license/backend/Dockerfile .

# 指定版本号构建
docker build -t agilestar/ai-license-mgr:1.0.0 -f license/backend/Dockerfile .

# 无缓存构建（依赖更新后使用）
docker build --no-cache -t agilestar/ai-license-mgr:latest -f license/backend/Dockerfile .
```

#### 独立运行

```bash
# 启动容器
docker run -d \
  --name ai-license-mgr \
  -p 8003:8003 \
  -v /data/ai_platform/licenses:/data/licenses:rw \
  -v /data/ai_platform/logs/license:/app/logs:rw \
  -e TZ=Asia/Shanghai \
  -e AI_LICENSE_DB=/data/licenses/license.db \
  --restart unless-stopped \
  agilestar/ai-license-mgr:latest

# 停止容器
docker stop ai-license-mgr

# 启动已停止的容器
docker start ai-license-mgr

# 重启容器
docker restart ai-license-mgr

# 删除容器
docker stop ai-license-mgr && docker rm ai-license-mgr
```

#### 验证

```bash
# 检查健康状态
curl http://localhost:8003/health

# 访问 Web 管理界面
# 浏览器打开：http://<server-ip>:8003
```

---

### 5.2 训练镜像 (ai-train)

**用途**：提供 GPU 训练环境，支持 PyTorch/PaddlePaddle 训练、模型导出和训练进度监控 Web UI。

**Dockerfile 路径**：`train/Dockerfile`

**基础镜像**：`nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04`（默认）

> **CUDA 版本说明**：默认使用 CUDA 11.8，兼容性最广，完全支持 PyTorch 2.x 所有版本。
> 如需使用 CUDA 12.x，可通过 `--build-arg` 切换基础镜像。
>
> 支持的基础镜像（已验证）：
> - `nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04` — **默认推荐**，兼容 PyTorch 2.0-2.4、ONNXRuntime 1.18
> - `nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04` — 可选，支持最新 CUDA 特性

**暴露端口**：8001

**依赖服务**：Redis（作为 Celery 异步任务队列的 broker）

#### 构建命令

```bash
# 标准构建（默认 CUDA 11.8，较大，约 8-12 GB，含 CUDA + cuDNN）
docker build -t agilestar/ai-train:latest -f train/Dockerfile .

# 使用 CUDA 12.1 构建（可选）
docker build -t agilestar/ai-train:latest -f train/Dockerfile \
  --build-arg CUDA_BASE_IMAGE=nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04 .

# 指定版本号
docker build -t agilestar/ai-train:1.0.0 -f train/Dockerfile .

# 无缓存构建
docker build --no-cache -t agilestar/ai-train:latest -f train/Dockerfile .
```

#### 独立运行

```bash
# 需要先启动 Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 启动训练容器（GPU 模式）
docker run -d \
  --name ai-train \
  --gpus all \
  -p 8001:8001 \
  -v /data/ai_platform/datasets:/workspace/datasets:ro \
  -v /data/ai_platform/models:/workspace/models:rw \
  -v /data/ai_platform/logs/train:/workspace/logs:rw \
  -e TZ=Asia/Shanghai \
  -e DATASETS_ROOT=/workspace/datasets \
  -e MODELS_ROOT=/workspace/models \
  -e REDIS_URL=redis://redis:6379/0 \
  --link redis:redis \
  --restart unless-stopped \
  agilestar/ai-train:latest

# 停止
docker stop ai-train

# 启动
docker start ai-train

# 重启
docker restart ai-train

# 删除
docker stop ai-train && docker rm ai-train
```

#### 验证

```bash
# 检查健康状态
curl http://localhost:8001/health

# 检查 GPU 是否可用（在容器内）
docker exec ai-train nvidia-smi
docker exec ai-train python3 -c "import torch; print(torch.cuda.is_available())"

# 访问训练管理 Web 界面
# 浏览器打开：http://<server-ip>:8001
```

---

### 5.3 训练开发镜像 (ai-train-dev)

**用途**：本地开发/调试用轻量训练镜像，无 CUDA 依赖，适合在笔记本/无 GPU 服务器上运行。

**Dockerfile 路径**：`train/Dockerfile.dev`

**基础镜像**：`python:3.11-slim`

**暴露端口**：8001

#### 构建命令

```bash
# 标准构建（较小，约 1-2 GB）
docker build -t agilestar/ai-train-dev:latest -f train/Dockerfile.dev .

# 指定版本号
docker build -t agilestar/ai-train-dev:1.0.0 -f train/Dockerfile.dev .
```

#### 独立运行

```bash
# 需要先启动 Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 启动训练开发容器（CPU 模式）
docker run -d \
  --name ai-train-dev \
  -p 8001:8001 \
  -v /data/ai_platform/datasets:/workspace/datasets:ro \
  -v /data/ai_platform/models:/workspace/models:rw \
  -v /data/ai_platform/logs/train:/workspace/logs:rw \
  -e TZ=Asia/Shanghai \
  -e DATASETS_ROOT=/workspace/datasets \
  -e MODELS_ROOT=/workspace/models \
  -e REDIS_URL=redis://redis:6379/0 \
  --link redis:redis \
  --restart unless-stopped \
  agilestar/ai-train-dev:latest

# 停止
docker stop ai-train-dev

# 启动
docker start ai-train-dev

# 重启
docker restart ai-train-dev

# 删除
docker stop ai-train-dev && docker rm ai-train-dev
```

#### 验证

```bash
curl http://localhost:8001/health
```

---

### 5.4 测试镜像 (ai-test)

**用途**：提供模型测试与精度评估服务，支持单样本测试、批量精度评估、版本对比和结果可视化。

**Dockerfile 路径**：`test/Dockerfile`

**基础镜像**：`python:3.11-slim`

**暴露端口**：8002

#### 构建命令

```bash
# 标准构建
docker build -t agilestar/ai-test:latest -f test/Dockerfile .

# 指定版本号
docker build -t agilestar/ai-test:1.0.0 -f test/Dockerfile .

# 无缓存构建
docker build --no-cache -t agilestar/ai-test:latest -f test/Dockerfile .
```

#### 独立运行

```bash
# 启动测试容器
docker run -d \
  --name ai-test \
  -p 8002:8002 \
  -v /data/ai_platform/models:/workspace/models:ro \
  -v /data/ai_platform/datasets:/workspace/datasets:ro \
  -v /data/ai_platform/logs/test:/workspace/logs:rw \
  -e TZ=Asia/Shanghai \
  -e MODELS_ROOT=/workspace/models \
  -e DATASETS_ROOT=/workspace/datasets \
  --restart unless-stopped \
  agilestar/ai-test:latest

# 停止
docker stop ai-test

# 启动
docker start ai-test

# 重启
docker restart ai-test

# 删除
docker stop ai-test && docker rm ai-test
```

#### 验证

```bash
# 检查健康状态
curl http://localhost:8002/health

# 访问测试管理 Web 界面
# 浏览器打开：http://<server-ip>:8002
```

---

### 5.5 编译镜像 (ai-builder-linux-x86)

**用途**：提供 C++ 编译环境 + Web 编译管理界面，将 AI 能力插件编译为 SO 动态库（Linux x86_64 平台）。支持在 Web 页面上选择 AI 能力、绑定客户密钥对，自动将客户公钥指纹编译到 SO 库中。

**Dockerfile 路径**：`build/Dockerfile.linux_x86`（两阶段构建：Node.js 编译前端 + Ubuntu 编译环境运行后端）

**基础镜像**：`node:18-slim`（前端构建阶段）+ `ubuntu:22.04`（运行阶段）

**暴露端口**：8004（Web 管理界面 + API）

**内含工具**：GCC 12、CMake、Ninja、OpenSSL、ONNXRuntime 1.18.1

**Web 管理界面功能**：
- 📊 仪表盘：查看可编译能力数、客户密钥对数、编译统计
- 🔨 新建编译：选择 AI 能力 + 绑定客户密钥对（自动计算公钥指纹写入 SO）+ 触发编译
- 📋 编译历史：查看编译状态、日志、下载编译产物

**API 端点**：
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/capabilities` | 列出所有可编译的 AI 能力 |
| GET | `/api/v1/key-pairs` | 代理获取授权服务的客户密钥对列表 |
| POST | `/api/v1/builds` | 触发编译（支持 key_pair_id 自动绑定公钥指纹） |
| GET | `/api/v1/builds` | 列出所有编译任务 |
| GET | `/api/v1/builds/{id}` | 查看编译任务状态 |
| GET | `/api/v1/builds/{id}/logs` | 获取编译日志 |
| GET | `/api/v1/builds/{id}/artifacts` | 列出编译产物 |
| GET | `/api/v1/builds/{id}/artifacts/{filename}` | 下载编译产物 |
| WS | `/ws/build/{id}` | WebSocket 实时编译日志流 |

#### 构建命令

```bash
# 标准构建（含前端 + 后端）
docker build -t agilestar/ai-builder-linux-x86:latest -f build/Dockerfile.linux_x86 .

# 指定版本号
docker build -t agilestar/ai-builder-linux-x86:1.0.0 -f build/Dockerfile.linux_x86 .

# 无缓存构建
docker build --no-cache -t agilestar/ai-builder-linux-x86:latest -f build/Dockerfile.linux_x86 .
```

#### docker compose 方式运行（推荐）

编译服务已集成到 `deploy/docker-compose.yml`，依赖授权服务获取客户密钥对：

```bash
cd deploy

# 启动全部服务（含编译管理）
docker compose up -d

# 仅启动编译 + 授权服务
docker compose up -d license build

# 查看编译服务日志
docker compose logs -f build

# 重启编译服务
docker compose restart build

# 停止编译服务
docker compose stop build
```

访问编译管理 Web 界面：`http://<宿主机IP>:8004`

#### 独立运行

```bash
# 启动编译服务容器
docker run -d \
  --name ai-builder \
  -p 8004:8004 \
  -v /data/ai_platform/libs/linux_x86_64:/workspace/libs/linux_x86_64:rw \
  -v /data/ai_platform/logs/build:/app/build/backend/data/build_logs:rw \
  -e TZ=Asia/Shanghai \
  -e LICENSE_SERVICE_URL=http://license:8003 \
  -e ONNXRUNTIME_ROOT=/usr/local \
  --restart unless-stopped \
  agilestar/ai-builder-linux-x86:latest

# 停止
docker stop ai-builder

# 启动
docker start ai-builder

# 重启
docker restart ai-builder

# 删除
docker stop ai-builder && docker rm ai-builder
```

#### 交互式编译（进入容器手动编译）

```bash
# 进入编译容器
docker run -it --rm \
  -v $(pwd)/cpp:/workspace/cpp:ro \
  -v /data/ai_platform/libs/linux_x86_64:/workspace/libs/linux_x86_64:rw \
  -e ONNXRUNTIME_ROOT=/usr/local \
  agilestar/ai-builder-linux-x86:latest \
  /bin/bash

# 容器内执行编译
cd /workspace/cpp
mkdir build && cd build
cmake .. -GNinja -DCMAKE_BUILD_TYPE=Release
ninja -j$(nproc)

# 编译特定能力
ninja recapture_detect
ninja face_detect
```

#### 验证

```bash
# 检查编译工具版本
docker exec ai-builder gcc --version
docker exec ai-builder cmake --version

# 检查 ONNXRuntime
docker exec ai-builder ls /usr/local/lib/libonnxruntime*

# 检查健康状态
curl http://localhost:8004/health

# 检查 Web 界面
curl -s http://localhost:8004/ | head -5

# 检查 API — 列出可编译能力
curl http://localhost:8004/api/v1/capabilities

# 检查 API — 查看编译历史
curl http://localhost:8004/api/v1/builds
```

---

### 5.6 生产推理镜像 (ai-prod)

**用途**：生产环境 AI 推理服务，提供 REST API 接口 + Web 管理页面（API 测试、AI 编排管理）、GPU/CPU 自适应、实例池并发调度、热重载。

**Dockerfile 路径**：`prod/Dockerfile`（两阶段构建：Node.js 编译前端 + Python 运行后端）

**基础镜像**：`ubuntu:22.04`

**暴露端口**：8080

**入口脚本**：`docker-entrypoint.sh`（自动检测 GPU 并配置推理后端）

**Web 管理页面**：访问 `http://<host>:8080/` 打开生产服务管理页面，支持：
- 📊 仪表盘：服务状态概览、能力统计、License 信息
- 🧪 API 测试：选择 AI 能力、上传图片、在线推理测试
- 🔗 AI 编排管理：创建/编辑/删除 AI 能力编排 Pipeline
- 🧪 编排测试：测试 Pipeline 编排执行效果
- 📋 服务状态：能力加载列表、License 详情
- ⚙️ 系统管理：热重载操作

#### 构建命令

```bash
# 标准构建
docker build -t agilestar/ai-prod:latest -f prod/Dockerfile .

# 指定版本号
docker build -t agilestar/ai-prod:1.0.0 -f prod/Dockerfile .

# 无缓存构建
docker build --no-cache -t agilestar/ai-prod:latest -f prod/Dockerfile .
```

#### 独立运行

```bash
# GPU 模式启动
docker run -d \
  --name ai-prod \
  --gpus all \
  -p 8080:8080 \
  -v /data/ai_platform/models:/mnt/ai_platform/models:ro \
  -v /data/ai_platform/libs/linux_x86_64:/mnt/ai_platform/libs:ro \
  -v /data/ai_platform/licenses:/mnt/ai_platform/licenses:ro \
  -v /data/ai_platform/pipelines:/mnt/ai_platform/pipelines:rw \
  -v /data/ai_platform/logs/prod:/mnt/ai_platform/logs:rw \
  -e TZ=Asia/Shanghai \
  -e AI_MAX_INSTANCES=4 \
  -e AI_ACQUIRE_TIMEOUT_S=30 \
  -e AI_ADMIN_TOKEN=your-secure-token-here \
  --restart always \
  agilestar/ai-prod:latest

# CPU 模式启动（去掉 --gpus）
docker run -d \
  --name ai-prod \
  -p 8080:8080 \
  -v /data/ai_platform/models:/mnt/ai_platform/models:ro \
  -v /data/ai_platform/libs/linux_x86_64:/mnt/ai_platform/libs:ro \
  -v /data/ai_platform/licenses:/mnt/ai_platform/licenses:ro \
  -v /data/ai_platform/pipelines:/mnt/ai_platform/pipelines:rw \
  -v /data/ai_platform/logs/prod:/mnt/ai_platform/logs:rw \
  -e TZ=Asia/Shanghai \
  -e AI_MAX_INSTANCES=4 \
  -e AI_ACQUIRE_TIMEOUT_S=30 \
  -e AI_ADMIN_TOKEN=your-secure-token-here \
  --restart always \
  agilestar/ai-prod:latest

# 停止
docker stop ai-prod

# 启动
docker start ai-prod

# 重启（平缓重启，不中断正在处理的请求）
docker restart ai-prod

# 删除
docker stop ai-prod && docker rm ai-prod
```

#### 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_BACKEND` | `auto` | 推理后端，auto=自动检测GPU，`onnxruntime-gpu`/`onnxruntime-cpu` |
| `AI_MAX_INSTANCES` | `4` | 每能力推理实例池大小 |
| `AI_ACQUIRE_TIMEOUT_S` | `30` | 实例获取超时秒数 |
| `AI_ADMIN_TOKEN` | `changeme` | 管理接口鉴权 Token（**务必修改**） |
| `UVICORN_WORKERS` | `2` | HTTP 工作进程数 |
| `LOG_LEVEL` | `info` | 日志级别 (debug/info/warning/error) |
| `MOUNT_ROOT` | `/mnt/ai_platform` | 挂载资源根目录 |
| `BUILTIN_ROOT` | `/app` | 内置资源根目录 |
| `AI_LICENSE_PATH` | `/mnt/ai_platform/licenses/license.bin` | License 文件路径 |
| `AI_PUBKEY_PATH` | `/mnt/ai_platform/licenses/pubkey.pem` | 公钥文件路径（用于签名验证） |
| `TRUSTED_PUBKEY_SHA256` | `""` | 受信公钥 SHA-256 指纹（64 位 hex）。设置后拒绝不匹配的公钥，防伪造 |

#### 验证

```bash
# 健康检查
curl http://localhost:8080/api/v1/health

# 查看已加载能力列表
curl http://localhost:8080/api/v1/capabilities

# 查看授权状态
curl http://localhost:8080/api/v1/license/status

# 测试推理（以 recapture_detect 为例）
curl -X POST http://localhost:8080/api/v1/infer/recapture_detect \
  -H "Content-Type: application/json" \
  -d '{"image": "<base64-encoded-image>"}'

# 热重载（需要管理 Token）
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer your-secure-token-here"
```

---

## 6. 开发环境启停管理 (docker-compose)

开发环境使用 `deploy/docker-compose.yml`，包含训练、测试、授权管理和 Redis 四个服务。

### 6.1 启动所有服务

```bash
cd deploy

# 前台启动（可看到实时日志）
docker compose up

# 后台启动
docker compose up -d

# 仅启动指定服务
docker compose up -d license        # 仅启动授权管理
docker compose up -d train redis    # 启动训练 + Redis
docker compose up -d test           # 仅启动测试
docker compose up -d license build  # 启动编译管理（依赖授权服务）
```

### 6.2 停止服务

```bash
cd deploy

# 停止所有服务（保留容器）
docker compose stop

# 停止并删除容器、网络
docker compose down

# 停止并删除容器、网络、卷（⚠️ 慎用：会删除 Redis 数据）
docker compose down -v

# 停止指定服务
docker compose stop train
docker compose stop test
docker compose stop license
docker compose stop build
```

### 6.3 重启服务

```bash
cd deploy

# 重启所有服务
docker compose restart

# 重启指定服务
docker compose restart train
docker compose restart test
docker compose restart license
docker compose restart build
```

### 6.4 查看服务状态

```bash
cd deploy

# 查看所有服务状态
docker compose ps

# 查看详细运行信息
docker compose ps -a
```

### 6.5 扩缩容

```bash
cd deploy

# 将测试服务扩展到 2 个实例（如果需要并行测试）
docker compose up -d --scale test=2
```

### 6.6 重新构建后启动

```bash
cd deploy

# 重新构建并启动（代码变更后）
docker compose up -d --build

# 仅重建指定服务
docker compose up -d --build license    # 授权管理
docker compose up -d --build train      # 训练
docker compose up -d --build test       # 测试
docker compose up -d --build build      # 编译管理
```

---

## 7. 生产环境启停管理 (docker-compose.prod)

生产环境使用 `deploy/docker-compose.prod.yml`，仅包含生产推理服务（含 Web 管理页面和 AI 编排引擎）。

### 7.1 启动

```bash
cd deploy

# 后台启动生产服务
docker compose -f docker-compose.prod.yml up -d

# 指定 GPU 架构和管理 Token
AI_ARCH=linux_x86_64 \
AI_MAX_INSTANCES=8 \
AI_ADMIN_TOKEN=your-secure-token \
docker compose -f docker-compose.prod.yml up -d

# 启动后访问管理页面
# Web 管理页面: http://<host>:8080/
# API 文档:     http://<host>:8080/api/v1/docs
```

### 7.2 停止

```bash
cd deploy

# 停止生产服务
docker compose -f docker-compose.prod.yml stop

# 停止并删除容器
docker compose -f docker-compose.prod.yml down
```

### 7.3 重启

```bash
cd deploy

# 重启
docker compose -f docker-compose.prod.yml restart
```

### 7.4 查看状态

```bash
cd deploy

docker compose -f docker-compose.prod.yml ps
```

### 7.5 热重载（不停服更新模型/SO）

```bash
# 1. 将新的模型或 SO 文件放到宿主机挂载目录
cp new_model.onnx /data/ai_platform/models/face_detect/v2/model.onnx

# 2. 通过 API 触发热重载
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer your-secure-token"

# 3. 验证新版本已加载
curl http://localhost:8080/api/v1/capabilities
```

### 7.6 无 GPU 的生产部署

编辑 `docker-compose.prod.yml`，注释掉 GPU 相关配置：

```yaml
services:
  prod:
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
```

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## 8. 日志管理

> **日志架构**：每个服务使用 Python `logging` 模块同时输出到 **文件** 和 **stdout**。
> 文件日志通过 Docker 卷挂载持久化到宿主机，stdout 日志由 Docker json-file 驱动管理。

### 8.1 应用日志文件路径

每个服务会自动创建带轮转的日志文件，格式为 `时间 | 级别 | 模块 | 消息`：

| 服务 | 容器内路径 | 宿主机路径 | 轮转策略 |
|------|-----------|-----------|---------|
| 授权管理 | `/app/logs/license.log` | `/data/ai_platform/logs/license/license.log` | 50MB × 5 |
| 训练 | `/workspace/logs/train.log` | `/data/ai_platform/logs/train/train.log` | 50MB × 5 |
| 测试 | `/workspace/logs/test.log` | `/data/ai_platform/logs/test/test.log` | 50MB × 5 |
| 编译 | `./data/build_logs/build_service.log` | `/data/ai_platform/logs/build/build_service.log` | 50MB × 5 |
| 生产推理 | `/mnt/ai_platform/logs/prod.log` | `/data/ai_platform/logs/prod/prod.log` | 50MB × 10 |

**日志包含内容**：
- ✅ 每个 HTTP 请求的 Method、Path、状态码、耗时
- ✅ 参数校验错误的详细字段信息
- ✅ 未捕获异常的完整堆栈跟踪
- ✅ 服务启停事件
- ✅ 能力加载/重载结果

### 8.2 查看宿主机日志文件

```bash
# 授权管理日志（排查"添加客户失败"等问题）
tail -f /data/ai_platform/logs/license/license.log

# 训练日志
tail -f /data/ai_platform/logs/train/train.log

# 测试日志
tail -f /data/ai_platform/logs/test/test.log

# 生产推理日志
tail -f /data/ai_platform/logs/prod/prod.log

# 搜索错误日志
grep "ERROR" /data/ai_platform/logs/license/license.log
grep "Validation error" /data/ai_platform/logs/license/license.log

# 查看最近 N 行
tail -100 /data/ai_platform/logs/prod/prod.log
```

### 8.3 查看容器实时日志（stdout）

```bash
# docker compose 方式（开发环境）
cd deploy
docker compose logs -f                  # 所有服务日志
docker compose logs -f train            # 训练服务日志
docker compose logs -f test             # 测试服务日志
docker compose logs -f license          # 授权服务日志

# docker compose 方式（生产环境）
docker compose -f docker-compose.prod.yml logs -f

# docker 原生方式
docker logs -f ai-train                 # 实时跟踪
docker logs --tail 100 ai-train         # 最近 100 行
docker logs --since 1h ai-train         # 最近 1 小时
docker logs --since 2026-03-28T10:00:00 ai-train  # 指定时间之后
docker logs -f --until 2026-03-28T12:00:00 ai-train  # 指定时间之前
```

### 8.4 Docker 日志文件位置

Docker 容器的 stdout/stderr 日志默认保存在：

```bash
# 查找容器日志文件
docker inspect --format='{{.LogPath}}' ai-prod
# 通常在：/var/lib/docker/containers/<container-id>/<container-id>-json.log
```

### 8.5 日志轮转配置

日志轮转已在 docker-compose 文件中配置：

| 环境 | 单文件大小 | 文件数量 | 总容量上限 |
|------|-----------|---------|-----------|
| 开发环境 | 50 MB | 5 | 250 MB/服务 |
| 生产环境 | 100 MB | 10 | 1 GB/服务 |

### 8.6 清理旧日志

```bash
# 清理指定容器的 Docker 日志（需要 root）
sudo truncate -s 0 $(docker inspect --format='{{.LogPath}}' ai-prod)

# 清理宿主机应用日志（按日期）
find /data/ai_platform/logs -name "*.log" -mtime +30 -delete
```

---

## 9. 健康检查

### 9.1 手动健康检查

```bash
# 授权管理服务
curl -sf http://localhost:8003/health && echo "OK" || echo "FAIL"

# 训练服务
curl -sf http://localhost:8001/health && echo "OK" || echo "FAIL"

# 测试服务
curl -sf http://localhost:8002/health && echo "OK" || echo "FAIL"

# 编译服务
curl -sf http://localhost:8004/health && echo "OK" || echo "FAIL"

# 生产推理服务
curl -sf http://localhost:8080/api/v1/health && echo "OK" || echo "FAIL"
```

### 9.2 一键健康检查脚本

项目内置了综合健康检查脚本 `scripts/health_check.sh`，可一键检查所有服务的容器状态、
HTTP 健康端点、GPU 状态和磁盘使用情况。

```bash
# 检查所有服务（开发 + 生产）
bash scripts/health_check.sh

# 仅检查开发环境服务（license/train/test/build）
bash scripts/health_check.sh dev

# 仅检查生产环境服务（prod）
bash scripts/health_check.sh prod

# 指定远程主机地址
DEV_HOST=192.168.1.100 bash scripts/health_check.sh dev
PROD_HOST=10.0.0.50 bash scripts/health_check.sh prod

# 自定义超时时间（默认 5 秒）
TIMEOUT=10 bash scripts/health_check.sh
```

脚本检查内容：

| 检查项 | 说明 |
|--------|------|
| 容器状态 | 通过 `docker inspect` 检查容器运行状态和健康检查状态 |
| HTTP 健康端点 | 调用各服务 `/health` 或 `/api/v1/health` 端点 |
| GPU 状态 | 通过 `nvidia-smi` 检查 GPU 显存和使用率 |
| 磁盘空间 | 检查 `/data/ai_platform` 分区使用率（>80% 警告，>95% 严重） |

输出示例：

```
════════════════════════════════════════════════════════════
  AI 能力平台 — 服务健康检查
  2026-03-29 15:30:00
════════════════════════════════════════════════════════════

【开发环境服务】 Host: localhost

  容器状态：
  ai-license-mgr       docker inspect ... ✅ RUNNING (healthy)
  ai-train             docker inspect ... ✅ RUNNING (healthy)
  ai-test              docker inspect ... ✅ RUNNING (healthy)
  ai-builder           docker inspect ... ✅ RUNNING (healthy)
  ai-redis             docker inspect ... ✅ RUNNING

  HTTP 健康检查：
  License (8003)       http://localhost:8003/health ... ✅ OK (ok)
  Train   (8001)       http://localhost:8001/health ... ✅ OK (ok)
  Test    (8002)       http://localhost:8002/health ... ✅ OK (ok)
  Build   (8004)       http://localhost:8004/health ... ✅ OK (ok)

────────────────────────────────────────────────────────────
  总计: 10 项检查
  ✅ 通过: 9  ❌ 失败: 0  ⏭️  跳过: 1
────────────────────────────────────────────────────────────

所有服务运行正常。
```

### 9.3 Docker 内置健康检查

docker-compose 文件中已为所有服务配置了健康检查，可通过以下方式查看：

```bash
# 查看健康状态
docker inspect --format='{{.State.Health.Status}}' ai-prod
# 输出：healthy / unhealthy / starting

# 查看健康检查日志
docker inspect --format='{{json .State.Health}}' ai-prod | python3 -m json.tool
```

健康检查参数：

| 服务 | 检查端点 | 间隔 | 超时 | 重试次数 | 启动宽限期 |
|------|---------|------|------|---------|-----------|
| license | `/health` | 30s | 10s | 3 | 15s |
| train | `/health` | 30s | 10s | 3 | 30s |
| test | `/health` | 30s | 10s | 3 | 15s |
| prod | `/api/v1/health` | 30s | 10s | 3 | 20s |

---

## 10. 镜像推送与仓库管理

### 10.1 一键构建并推送所有镜像

```bash
# 使用内置脚本
./scripts/build_and_push.sh <REGISTRY> <VERSION>

# 示例：推送到公司镜像仓库
./scripts/build_and_push.sh registry.agilestar.cn/ai-platform 1.0.0
```

脚本会依次构建并推送以下镜像：

1. `<REGISTRY>/ai-license-mgr:<VERSION>` + `:latest`
2. `<REGISTRY>/ai-train:<VERSION>` + `:latest`
3. `<REGISTRY>/ai-test:<VERSION>` + `:latest`
4. `<REGISTRY>/ai-prod:<VERSION>` + `:latest`

### 10.2 手动推送到私有仓库

```bash
# 登录私有仓库
docker login registry.agilestar.cn

# 标记镜像
docker tag agilestar/ai-prod:latest registry.agilestar.cn/ai-platform/ai-prod:1.0.0
docker tag agilestar/ai-prod:latest registry.agilestar.cn/ai-platform/ai-prod:latest

# 推送
docker push registry.agilestar.cn/ai-platform/ai-prod:1.0.0
docker push registry.agilestar.cn/ai-platform/ai-prod:latest
```

### 10.3 镜像导出与离线传输

```bash
# 导出镜像为 tar 文件（用于离线交付）
docker save agilestar/ai-prod:1.0.0 | gzip > ai-prod-1.0.0.tar.gz
docker save agilestar/ai-license-mgr:1.0.0 | gzip > ai-license-mgr-1.0.0.tar.gz
docker save agilestar/ai-train:1.0.0 | gzip > ai-train-1.0.0.tar.gz
docker save agilestar/ai-test:1.0.0 | gzip > ai-test-1.0.0.tar.gz
docker save agilestar/ai-builder-linux-x86:1.0.0 | gzip > ai-builder-1.0.0.tar.gz

# 在目标服务器导入
docker load < ai-prod-1.0.0.tar.gz
docker load < ai-license-mgr-1.0.0.tar.gz
```

### 10.4 镜像清理

```bash
# 删除本地所有 agilestar 相关镜像
docker images "agilestar/*" --format "{{.Repository}}:{{.Tag}}" | xargs -r docker rmi

# 删除悬挂（dangling）镜像
docker image prune -f

# 深度清理（⚠️ 慎用：删除所有未使用的镜像、容器、网络）
docker system prune -a --volumes
```

---

## 11. 交付包打包

### 11.1 使用打包脚本

```bash
# 打包完整交付包
./scripts/package_delivery.sh <VERSION> [OUTPUT_DIR]

# 示例
./scripts/package_delivery.sh 1.0.0 /tmp/delivery_1.0.0
```

### 11.2 交付包内容

> **重要**：推理 SO（`libai_runtime.so`）和生产镜像中硬编码了该客户公钥的 SHA-256
> 指纹，因此**每个客户的交付包中 SO 和镜像都是该客户专属的**。详见
> [附录：授权安全模型](#16-附录授权安全模型)。

```
delivery_package/
├── docker/
│   └── agilestar-ai-prod-linux-x86_64-v1.0.0-<客户>.tar.gz  # 客户专属生产镜像
├── libs/
│   └── linux_x86_64/
│       └── libai_runtime.so              # 客户专属推理 SO（含公钥指纹）
├── docs/
│   ├── ai_capability_market_overview.md  # AI 能力超市总览
│   ├── docker_operations_manual.md       # 本手册
│   └── design/                           # 设计文档
├── sdk_linux_x86_64/include/agilestar/  # C/C++ SDK 头文件
├── tools/
│   └── license_tool                      # 机器指纹采集工具
├── mount_template/
│   ├── init_host_dirs.sh                 # 宿主机目录初始化脚本
│   └── README.md
└── DELIVERY_MANIFEST.txt                 # 交付清单和部署说明
```

### 11.3 客户交付标准流程（⭐ 每客户必须执行）

> **安全模型：公钥指纹硬编码 + 运行时挂载**
>
> 为防止攻击者自行伪造密钥对和授权文件来绕过签名验证，我们将**客户公钥的
> SHA-256 指纹硬编码**进推理 SO 和生产镜像中。这意味着：
>
> - 即使攻击者替换了 `pubkey.pem` 和 `license.bin`，SO 和 Python 服务
>   都会检测到公钥指纹不匹配，**拒绝验证**。
> - **每个新客户交付前**，必须用该客户公钥的指纹重新编译 SO / 重建镜像。
> - 密钥轮换时也需重新编译 SO / 重建镜像。

#### 标准流程（研发侧操作）

```bash
# =====================================================================
# 客户交付标准流程
# =====================================================================

# 步骤 1：创建客户专属密钥对
#   前端：🔑 密钥管理 → 生成新密钥对
#   名称建议：customer-<客户简称>-<年份>，如 customer-huawei-2026
#   私钥保存路径（容器内路径）：/data/licenses/keys/<客户简称>/private_key.pem
#   对应宿主机路径：/data/ai_platform/licenses/keys/<客户简称>/private_key.pem

# 步骤 2：下载该客户公钥
#   前端"下载公钥"按钮 → 保存为 pubkey.pem

# 步骤 3：计算该客户公钥的 SHA-256 指纹
python3 scripts/compute_pubkey_fingerprint.py /path/to/customer/pubkey.pem
# 输出示例：a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890

# 步骤 4：用该指纹重新编译推理 SO（libai_runtime.so）
cd cpp
mkdir -p build && cd build
cmake .. \
  -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DTRUSTED_PUBKEY_SHA256=<步骤3输出的指纹>
ninja ai_runtime
# 编译产物：build/lib/libai_runtime.so

# 步骤 5：用该指纹重建生产 Docker 镜像
#   方式 A：通过 ARG 注入（推荐）
docker build \
  -t agilestar/ai-prod:1.0.0-<客户简称> \
  -f prod/Dockerfile \
  --build-arg TRUSTED_PUBKEY_SHA256=<步骤3输出的指纹> \
  .

#   方式 B：通过环境变量（运行时注入，镜像通用但安全性略低）
docker run -d \
  --name ai-prod \
  -e TRUSTED_PUBKEY_SHA256=<步骤3输出的指纹> \
  ... \
  agilestar/ai-prod:1.0.0

# 步骤 6：生成该客户的 License 文件
#   前端：➕ 生成授权 → 选择步骤1创建的密钥对 → 配置能力和有效期
#   下载 license.bin

# 步骤 7：打包交付
./scripts/package_delivery.sh 1.0.0 /tmp/delivery_<客户简称>
# 将步骤4编译的 SO 覆盖进交付包的 libs/ 目录
# 将步骤5构建的镜像导出进交付包的 docker/ 目录
# 将 pubkey.pem 和 license.bin 一并交付

# 步骤 8：导出客户专属镜像
docker save agilestar/ai-prod:1.0.0-<客户简称> | gzip > \
  /tmp/delivery_<客户简称>/docker/agilestar-ai-prod-linux-x86_64-v1.0.0-<客户简称>.tar.gz
```

#### 客户端部署步骤

```bash
# 1. 初始化宿主机目录
sudo bash mount_template/init_host_dirs.sh

# 2. 导入客户专属 Docker 镜像
docker load < docker/agilestar-ai-prod-linux-x86_64-v1.0.0-<客户简称>.tar.gz

# 3. 放置客户公钥
sudo cp pubkey.pem /data/ai_platform/licenses/

# 4. 放置 License 文件
sudo cp license.bin /data/ai_platform/licenses/

# 5. 放置模型包
cp -r models/* /data/ai_platform/models/

# 6. 放置客户专属 SO 插件
cp -r libs/* /data/ai_platform/libs/linux_x86_64/

# 7. 启动服务
docker run -d \
  --name ai-prod \
  --gpus all \
  -p 8080:8080 \
  -v /data/ai_platform/models:/mnt/ai_platform/models:ro \
  -v /data/ai_platform/libs/linux_x86_64:/mnt/ai_platform/libs:ro \
  -v /data/ai_platform/licenses:/mnt/ai_platform/licenses:ro \
  -v /data/ai_platform/logs/prod:/mnt/ai_platform/logs:rw \
  -e AI_ADMIN_TOKEN=your-secure-token \
  --restart always \
  agilestar/ai-prod:1.0.0-<客户简称>

# 8. 验证
curl http://localhost:8080/api/v1/health
curl http://localhost:8080/api/v1/license/status
```

### 11.4 授权密钥对管理（一客户一密钥对 + 公钥指纹硬编码）

平台采用 **一客户一密钥对 + 公钥指纹硬编码** 安全模型：

| 概念 | 说明 |
|------|------|
| 密钥对粒度 | 每个客户分配一个独立的 RSA-2048 密钥对 |
| 私钥存储 | 仅存于内部授权管理服务器磁盘（`0o600` 权限），数据库中不存储 |
| 公钥存储 | 存于授权管理 DB（`key_pairs` 表），同时交付给客户 |
| 公钥指纹 | 公钥的 SHA-256 哈希硬编码进推理 SO 和生产镜像中，防止公钥被替换 |
| License 签名 | 使用客户对应密钥对的私钥签名，`license_records` 表记录 `key_pair_id` |
| 运行时验证 | ① 比对 `pubkey.pem` 的 SHA-256 与硬编码指纹 → ② RSA-PSS SHA256 签名验证 |
| SO 编译 | **每个客户交付前须重新编译** `libai_runtime.so`（注入该客户公钥指纹） |

**交付给客户的文件：**

```
/data/ai_platform/
├── licenses/
│   ├── pubkey.pem     ← 该客户密钥对的公钥（用于签名验证）
│   └── license.bin    ← 该客户的授权文件（包含 capabilities、有效期等）
└── libs/linux_x86_64/
    └── libai_runtime.so ← 该客户专属 SO（硬编码了该客户公钥指纹）
```

**防伪造攻击链路：**

```
┌──────────────────────────────────────────────────────────────┐
│  攻击者尝试：自建密钥对 → 伪造私钥签名 → 替换 pubkey.pem      │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
  SO / Python 服务加载 pubkey.pem
                       ▼
  SHA256(pubkey.pem) ≠ 硬编码的 TRUSTED_PUBKEY_SHA256
                       ▼
               ❌ 拒绝 — 公钥被篡改
```

**操作流程（参考 11.3 标准流程）：**

```bash
# 1. 在授权管理平台创建客户专属密钥对
# 2. 下载该客户的公钥 PEM
# 3. 计算公钥 SHA-256 指纹
python3 scripts/compute_pubkey_fingerprint.py pubkey.pem

# 4. 用指纹编译客户专属 SO
cmake .. -DTRUSTED_PUBKEY_SHA256=<指纹>
ninja ai_runtime

# 5. 用指纹构建客户专属生产镜像
docker build --build-arg TRUSTED_PUBKEY_SHA256=<指纹> ...

# 6. 生成授权时选择该客户密钥对 → 下载 license.bin
# 7. 交付：镜像 + SO + pubkey.pem + license.bin
```

**密钥轮换（⚠️ 需重新编译 SO）：**

```bash
# 如需轮换密钥（如疑似泄露），需要：
# 1. 生成新密钥对（旧密钥对标记为"停用"）
# 2. 计算新公钥指纹
python3 scripts/compute_pubkey_fingerprint.py new_pubkey.pem

# 3. 用新指纹重新编译 SO
cmake .. -DTRUSTED_PUBKEY_SHA256=<新指纹>
ninja ai_runtime

# 4. 用新指纹重建生产镜像
docker build --build-arg TRUSTED_PUBKEY_SHA256=<新指纹> ...

# 5. 用新密钥对重新签发授权
# 6. 将新的 SO + 镜像 + pubkey.pem + license.bin 交付给客户
# 其他客户完全不受影响
```

---

## 12. 常用运维命令速查表

### 镜像操作

| 操作 | 命令 |
|------|------|
| 查看所有平台镜像 | `docker images "agilestar/*"` |
| 构建训练镜像 | `docker build -t agilestar/ai-train:latest -f train/Dockerfile .` |
| 构建测试镜像 | `docker build -t agilestar/ai-test:latest -f test/Dockerfile .` |
| 构建授权镜像 | `docker build -t agilestar/ai-license-mgr:latest -f license/backend/Dockerfile .` |
| 构建编译镜像 | `docker build -t agilestar/ai-builder-linux-x86:latest -f build/Dockerfile.linux_x86 .` |
| 构建生产镜像 | `docker build -t agilestar/ai-prod:latest -f prod/Dockerfile .` |
| 导出镜像 | `docker save agilestar/ai-prod:latest \| gzip > ai-prod.tar.gz` |
| 导入镜像 | `docker load < ai-prod.tar.gz` |
| 查看镜像详情 | `docker inspect agilestar/ai-prod:latest` |
| 查看镜像大小 | `docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" "agilestar/*"` |

### 容器操作

| 操作 | 命令 |
|------|------|
| 查看所有运行中容器 | `docker ps` |
| 查看所有容器（含停止） | `docker ps -a` |
| 进入容器 Shell | `docker exec -it ai-prod /bin/bash` |
| 在容器中执行命令 | `docker exec ai-prod python3 -c "print('hello')"` |
| 查看容器资源使用 | `docker stats ai-prod` |
| 查看所有容器资源 | `docker stats` |
| 查看容器详细信息 | `docker inspect ai-prod` |
| 复制文件到容器 | `docker cp local_file.txt ai-prod:/app/` |
| 从容器复制文件 | `docker cp ai-prod:/app/logs/error.log ./` |

### 开发环境（docker-compose）

| 操作 | 命令 |
|------|------|
| 启动所有 | `cd deploy && docker compose up -d` |
| 停止所有 | `cd deploy && docker compose stop` |
| 重启所有 | `cd deploy && docker compose restart` |
| 停止并清理 | `cd deploy && docker compose down` |
| 查看状态 | `cd deploy && docker compose ps` |
| 查看所有日志 | `cd deploy && docker compose logs -f` |
| 查看单服务日志 | `cd deploy && docker compose logs -f train` |
| 重建并启动 | `cd deploy && docker compose up -d --build` |

### 生产环境（docker-compose.prod）

| 操作 | 命令 |
|------|------|
| 启动 | `cd deploy && docker compose -f docker-compose.prod.yml up -d` |
| 停止 | `cd deploy && docker compose -f docker-compose.prod.yml stop` |
| 重启 | `cd deploy && docker compose -f docker-compose.prod.yml restart` |
| 停止并清理 | `cd deploy && docker compose -f docker-compose.prod.yml down` |
| 查看日志 | `cd deploy && docker compose -f docker-compose.prod.yml logs -f` |

### 日志和调试

| 操作 | 命令 |
|------|------|
| 实时日志 | `docker logs -f ai-prod` |
| 最近 N 行 | `docker logs --tail 200 ai-prod` |
| 最近 N 小时 | `docker logs --since 2h ai-prod` |
| 宿主机训练日志 | `tail -f /data/ai_platform/logs/train/train.log` |
| 宿主机生产日志 | `tail -f /data/ai_platform/logs/prod/prod.log` |
| GPU 状态 | `docker exec ai-prod nvidia-smi` |
| 内存/CPU 监控 | `docker stats --no-stream` |
| 健康检查状态 | `docker inspect --format='{{.State.Health.Status}}' ai-prod` |

---

## 13. 新增 AI 能力模块完整操作流程

> 本节描述从零开始新增一个 AI 能力模块的完整端到端流程，确保所有子系统同步更新。

### 13.1 流程总览

```
训练 → 模型导出 → 测试验证 → C++插件开发 → 授权配置 → SO编译 → 生产集成 → AI编排(可选)
```

### 13.2 步骤 1：训练工作

```bash
# ── 1.1 准备代码 ──
# 创建训练脚本（必须手动完成）
mkdir -p train/scripts/<new_cap>/
# 需要创建：
#   train/scripts/<new_cap>/train.py       # 训练主脚本
#   train/scripts/<new_cap>/export.py      # 模型导出脚本（PyTorch → ONNX）
#   train/scripts/<new_cap>/config.json    # 默认训练超参数
#   train/scripts/<new_cap>/requirements.txt # 训练依赖

# ── 1.2 准备样本数据 ──
# 将训练数据放到宿主机指定位置
cp -r /path/to/training_data/* /data/ai_platform/datasets/<new_cap>/

# ── 1.3 启动训练容器 ──
cd deploy
docker compose up -d train redis

# ── 1.4 打开训练管理 Web 页面 ──
# 浏览器打开：http://<server-ip>:8001
# 操作步骤：
#   1. 进入"能力配置"页面，新能力会自动出现在列表中
#   2. 配置训练参数（学习率、batch_size、epoch 等）
#   3. 选择训练数据集路径
#   4. 点击"开始训练"

# ── 1.5 监控训练进度 ──
# 训练管理 Web 页面实时展示：
#   - Loss 曲线
#   - 训练进度百分比
#   - GPU 使用状态
#   - 实时日志
# 也可查看宿主机日志：
tail -f /data/ai_platform/logs/train/train.log

# ── 1.6 导出模型 ──
# 训练完成后，在 Web 页面执行模型导出
# 导出为 ONNX 格式（或根据具体能力选择合适的格式）
# 模型输出到：/data/ai_platform/models/<new_cap>/v1.0.0/
#   ├── model.onnx
#   └── manifest.json
```

### 13.3 步骤 2：测试模型

```bash
# ── 2.1 准备测试样本 ──
mkdir -p /data/ai_platform/datasets/<new_cap>/test/
cp -r /path/to/test_samples/* /data/ai_platform/datasets/<new_cap>/test/

# ── 2.2 添加测试推理器（必须手动完成）──
# 编辑 test/backend/inferencers.py
# 添加新能力的推理器类：
#   class NewCapInferencer(BaseInferencer):
#       def preprocess(self, input_data): ...
#       def postprocess(self, output): ...

# ── 2.3 启动测试容器 ──
cd deploy
docker compose up -d test

# ── 2.4 打开测试管理 Web 页面 ──
# 浏览器打开：http://<server-ip>:8002
# 操作步骤：
#   1. 新能力自动出现在模型列表中
#   2. 单样本测试：上传单个测试图片，查看推理结果
#   3. 批量测试：配置测试数据集路径，执行批量测试
#   4. 查看评估报告（精度、召回率、F1 等指标）
#   5. 版本对比：对比 v1.0.0 与之前版本的精度差异
```

### 13.4 步骤 3：授权生成

```bash
# ── 3.1 启动授权容器 ──
cd deploy
docker compose up -d license

# ── 3.2 打开授权管理 Web 页面 ──
# 浏览器打开：http://<server-ip>:8003
# 操作步骤：
#   1. 进入"授权生成"页面
#   2. 选择客户密钥对
#   3. 在能力列表中勾选新增的 AI 能力（自动出现在列表中）
#   4. 设置有效期
#   5. 点击"生成授权"→ 下载 license.bin

# ── 3.3 验证授权 ──
# 在授权管理页面查看生成的授权详情，确认包含新能力

# ── 3.4 输出授权文件 ──
cp license.bin /data/ai_platform/licenses/
```

### 13.5 步骤 4：推理库编译

```bash
# ── 4.1 准备 C++ 插件代码（必须手动完成）──
# 创建能力插件源码
mkdir -p cpp/capabilities/<new_cap>/
# 需要创建：
#   cpp/capabilities/<new_cap>/CMakeLists.txt   # 使用 add_capability_plugin 宏
#   cpp/capabilities/<new_cap>/<new_cap>.h      # 接口头文件
#   cpp/capabilities/<new_cap>/<new_cap>.cpp    # 实现（AiCreate/AiInit/AiInfer/AiDestroy等）

# ── 4.2 启动编译容器 ──
cd deploy
docker compose up -d license build

# ── 4.3 打开编译管理 Web 页面 ──
# 浏览器打开：http://<server-ip>:8004
# 操作步骤：
#   1. 新能力自动出现在可编译能力列表中（动态扫描 cpp/capabilities/ 目录）
#   2. 选择要编译的能力（勾选新增的能力）
#   3. 选择客户密钥对（授权绑定）
#   4. 确认授权信息中包含该新增的 AI 能力
#   5. 点击"开始编译"
#   6. 查看实时编译日志（WebSocket 推送）

# ── 4.4 编译产物自动归档 ──
# 编译成功后，SO 文件自动输出到：
# /data/ai_platform/libs/linux_x86_64/<new_cap>/lib<new_cap>.so
# 生产镜像通过卷挂载即可访问
```

### 13.6 步骤 5：生产镜像构建（仅首次）

```bash
# ── 仅在首次创建生产镜像时需要执行 ──

# 5.1 构建生产镜像
docker build -t agilestar/ai-prod:latest -f prod/Dockerfile .

# 5.2 启动生产镜像
cd deploy
AI_ADMIN_TOKEN=your-secure-token \
docker compose -f docker-compose.prod.yml up -d

# 5.3 打开生产 Web 管理页面
# 浏览器打开：http://<server-ip>:8080
# 操作步骤：
#   1. 仪表盘：确认新能力已加载
#   2. API 测试页面：选择新增的 AI 能力，上传测试图片，执行推理
#   3. 服务状态页面：确认能力状态为 "loaded"

# 5.4 使用 curl 测试 HTTP 接口
curl http://localhost:8080/api/v1/health
curl http://localhost:8080/api/v1/capabilities
curl -X POST http://localhost:8080/api/v1/infer/<new_cap> \
  -F "image=@/path/to/test.jpg"
```

### 13.7 步骤 6：已有镜像更新 AI 能力

```bash
# ── 已有生产镜像添加新 AI 能力时执行 ──

# 6.1 确认编译产物和模型已就位
ls -la /data/ai_platform/libs/linux_x86_64/<new_cap>/
ls -la /data/ai_platform/models/<new_cap>/v1.0.0/
ls -la /data/ai_platform/licenses/license.bin

# 6.2 重启生产镜像（加载新资源）
cd deploy
docker compose -f docker-compose.prod.yml restart

# 或通过热重载 API（无需重启容器）
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer your-secure-token"

# 6.3 验证新能力已加载
curl http://localhost:8080/api/v1/capabilities
# 应该在返回列表中看到新增的能力

# 6.4 在生产 Web 页面测试
# 浏览器打开：http://<server-ip>:8080
# → API 测试页面 → 选择新能力 → 上传测试图片 → 执行推理

# 6.5 使用 curl 测试接口
curl -X POST http://localhost:8080/api/v1/infer/<new_cap> \
  -F "image=@/path/to/test.jpg"
```

### 13.8 步骤 7：AI 能力编排（可选）

```bash
# ── 如需将新能力纳入 Pipeline 编排 ──

# 7.1 打开生产 Web 管理页面
# 浏览器打开：http://<server-ip>:8080
# → AI 编排管理页面

# 7.2 创建或更新 Pipeline
# 操作步骤：
#   1. 点击"新建编排"
#   2. 添加步骤，选择 AI 能力（新增的能力自动出现在列表中）
#   3. 配置步骤参数、条件分支、错误处理策略
#   4. 点击"验证"确认配置正确
#   5. 保存 Pipeline

# 7.3 测试编排
# → 编排测试页面 → 选择 Pipeline → 上传测试数据 → 执行
# 查看每个步骤的执行结果和最终输出

# 7.4 通过 API 测试编排
# 创建 Pipeline
curl -X POST http://localhost:8080/api/v1/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_id": "my_pipeline",
    "name": "示例编排",
    "steps": [
      {"step_id": "step1", "capability": "<new_cap>", "params": {}}
    ]
  }'

# 执行 Pipeline
curl -X POST http://localhost:8080/api/v1/pipeline/my_pipeline/run \
  -F "image=@/path/to/test.jpg"
```

### 13.9 全链路更新清单（每次新增能力必须检查）

| # | 更新内容 | 自动/手动 | 说明 |
|---|---------|----------|------|
| 1 | C++ 能力插件代码 | ⚠️ 手动 | `cpp/capabilities/<new_cap>/` |
| 2 | 训练脚本 | ⚠️ 手动 | `train/scripts/<new_cap>/train.py, export.py` |
| 3 | 测试推理器 | ⚠️ 手动 | `test/backend/inferencers.py` 添加推理器类 |
| 4 | 训练 Web 页面 | ✅ 自动 | 能力列表动态加载 |
| 5 | 测试 Web 页面 | ✅ 自动 | 模型列表动态扫描 |
| 6 | 授权 Web 页面 | ✅ 自动 | 能力列表动态读取 |
| 7 | 编译 Web 页面 | ✅ 自动 | 能力目录动态扫描 |
| 8 | 生产 Web 页面 | ✅ 自动 | 已加载能力动态展示 |
| 9 | AI 编排系统 | ✅ 自动 | 能力列表动态加载 |
| 10 | Pipeline 配置 | ⚠️ 手动 | 如需编排则创建 JSON 配置 |
| 11 | 能力清单文档 | ⚠️ 手动 | `docs/ai_capability_market_overview.md` |

---

## 14. 故障排查指南

### 14.1 容器无法启动

```bash
# 检查容器启动日志
docker logs ai-prod

# 检查完整启动信息
docker inspect ai-prod | grep -A 20 "State"

# 常见原因及解决方案：
# 1. 端口被占用
sudo lsof -i :8080
# → 更换端口或停止占用端口的进程

# 2. 挂载目录不存在
ls -la /data/ai_platform/
# → 执行 init_host_dirs.sh 初始化目录

# 3. 权限不足
sudo chmod -R 777 /data/ai_platform/logs/
# → 确保日志目录可写

# 4. GPU 不可用（GPU 模式下）
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 nvidia-smi
# → 检查 NVIDIA 驱动和 Container Toolkit
```

### 14.2 服务健康检查失败

```bash
# 检查容器是否运行
docker ps | grep ai-prod

# 查看健康检查详情
docker inspect --format='{{json .State.Health}}' ai-prod | python3 -m json.tool

# 进入容器手动测试
docker exec -it ai-prod curl -sf http://localhost:8080/api/v1/health

# 检查容器内部进程
docker exec ai-prod ps aux

# 检查端口监听
docker exec ai-prod ss -tlnp
```

### 14.3 推理返回错误

```bash
# 错误码 4002：License 已过期
# → 更新 License 文件到 /data/ai_platform/licenses/
curl http://localhost:8080/api/v1/license/status

# 错误码 4003：能力未授权
# → 检查 License 中授权的能力列表
curl http://localhost:8080/api/v1/capabilities

# 错误码 4004：机器指纹不匹配
# → 重新为当前服务器生成 License

# 错误码 4005：License 签名无效（含公钥指纹不匹配）
# → 检查 pubkey.pem 是否为该客户专属公钥
# → 检查生产镜像/SO 是否为该客户专属版本（含正确的 TRUSTED_PUBKEY_SHA256）
# → 如果更换过密钥对，须重新编译 SO 和重建镜像（参见 11.3 标准流程）
curl http://localhost:8080/api/v1/license/status

# 错误码 5002：模型加载失败
# → 检查模型文件是否存在且完整
ls -la /data/ai_platform/models/<capability>/<version>/
docker exec ai-prod ls -la /mnt/ai_platform/models/

# 错误码 5001：推理内部错误
# → 查看详细日志
docker logs --tail 100 ai-prod
tail -50 /data/ai_platform/logs/prod/prod.log
```

### 14.4 GPU 相关问题

```bash
# 检查宿主机 GPU 状态
nvidia-smi

# 检查 Docker GPU 支持
docker info | grep -i nvidia

# 测试 GPU 容器
docker run --rm --gpus all nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 nvidia-smi

# 容器内检查 GPU
docker exec ai-prod nvidia-smi
docker exec ai-train python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# NVIDIA Container Toolkit 未安装
# → 参考第 2.3 节安装步骤
```

### 14.5 磁盘空间不足

```bash
# 检查 Docker 磁盘使用
docker system df

# 清理已停止的容器
docker container prune -f

# 清理悬挂镜像
docker image prune -f

# 清理所有未使用的 Docker 资源
docker system prune -f

# 清理旧日志
find /data/ai_platform/logs -name "*.log" -size +100M -exec truncate -s 0 {} \;

# 查看镜像大小排名
docker images --format "{{.Size}}\t{{.Repository}}:{{.Tag}}" | sort -hr
```

### 14.6 训练服务 Celery Worker 异常

```bash
# 检查 Redis 连接
docker exec ai-train redis-cli -h redis ping

# 检查 Celery Worker 状态
docker exec ai-train celery -A tasks.celery_app inspect ping

# 查看 Celery Worker 日志
docker exec ai-train cat /workspace/logs/celery.log

# 重启 Celery Worker（容器内）
docker exec ai-train celery -A tasks.celery_app control shutdown
docker restart ai-train
```

### 14.7 网络连接问题

```bash
# 检查容器网络
docker network ls
docker network inspect deploy_default

# 检查容器间连通性
docker exec ai-train ping -c 3 redis
docker exec ai-train curl -sf http://license:8003/health

# 检查端口映射
docker port ai-prod
```

### 14.8 授权管理数据库迁移

授权管理后端使用 SQLite 数据库。版本升级后如果 SQLAlchemy 模型新增了字段（如
`key_pair_id`），服务会在启动时**自动执行 ALTER TABLE 迁移**，无需手动操作。

如果遇到 `no such column` 错误（如 `license_records.key_pair_id`），通常是因为
容器使用了旧镜像。解决步骤：

```bash
# 1. 确认使用最新代码重建镜像
cd deploy
docker compose build license

# 2. 重启服务（自动迁移会在启动时运行）
docker compose up -d license

# 3. 查看迁移日志，确认 ALTER TABLE 执行成功
docker logs ai-license-mgr 2>&1 | grep -i migrat

# 4. 如果仍有问题，可手动迁移（进入容器执行）
docker exec -it ai-license-mgr python3 -c "
import sqlite3, os
db = os.environ.get('AI_LICENSE_DB', '/data/licenses/license.db')
conn = sqlite3.connect(db)
cols = [r[1] for r in conn.execute('PRAGMA table_info(license_records)')]
if 'key_pair_id' not in cols:
    conn.execute('ALTER TABLE license_records ADD COLUMN key_pair_id INTEGER REFERENCES key_pairs(id)')
    conn.commit()
    print('key_pair_id column added')
else:
    print('key_pair_id column already exists')
conn.close()
"

# 5. 极端情况：删除旧数据库重新初始化（⚠️ 会丢失所有授权记录）
# docker exec ai-license-mgr rm -f /data/licenses/license.db
# docker restart ai-license-mgr
```

---

## 15. 附录：端口分配表

| 端口 | 服务 | 协议 | 环境 | 说明 |
|------|------|------|------|------|
| 8001 | ai-train / ai-train-dev | HTTP | 开发 | 训练管理 Web UI + API |
| 8002 | ai-test | HTTP | 开发 | 测试管理 Web UI + API |
| 8003 | ai-license-mgr | HTTP | 开发/生产 | 授权管理 Web UI + API |
| 8004 | ai-builder-linux-x86 | HTTP | 开发 | 编译管理 API |
| 8080 | ai-prod | HTTP | 生产 | 生产推理 REST API |
| 6379 | redis | TCP | 开发(内部) | Celery 任务队列（仅 localhost） |

> **安全提示**：生产环境中，8003（授权管理）不应暴露到公网。6379（Redis）仅绑定 `127.0.0.1`。

---

## 16. 附录：授权安全模型

### 16.1 威胁分析与防御

| 攻击场景 | 防御措施 |
|----------|---------|
| 伪造密钥对 + 替换公钥 + 伪造授权 | 公钥 SHA-256 指纹硬编码进 SO 和镜像，加载 pubkey.pem 时先比对指纹 |
| 篡改 license.bin 内容 | RSA-PSS SHA256 签名验证（私钥仅在授权管理服务器） |
| 篡改推理 SO 中的指纹 | SO 为编译后二进制，修改需要反编译和重新链接，难度极高 |
| 跨客户复制授权 | 每客户独立密钥对 + 独立 SO，密钥对互不通用 |
| 过期后继续使用 | License 中 `valid_until` 由签名保护，无法篡改 |

### 16.2 安全验证链路

```
┌─────────────────────────────────────────────────────────────────────┐
│ 推理请求到达                                                         │
│                                                                     │
│  1. 加载 /mnt/ai_platform/licenses/pubkey.pem                       │
│  2. 计算 SHA-256(pubkey.pem)                                        │
│  3. 比对硬编码的 TRUSTED_PUBKEY_SHA256                                │
│     ├─ 不匹配 → ❌ 拒绝（公钥被篡改）                                 │
│     └─ 匹配 ↓                                                       │
│  4. 加载 /mnt/ai_platform/licenses/license.bin                       │
│  5. 重建 canonical JSON payload                                      │
│  6. RSA-PSS SHA256 签名验证 (pubkey.pem vs license.bin.signature)     │
│     ├─ 失败 → ❌ 拒绝（签名无效）                                     │
│     └─ 成功 ↓                                                       │
│  7. 检查有效期 (valid_from, valid_until)                              │
│     ├─ 过期/未生效 → ❌ 拒绝                                         │
│     └─ 有效 ↓                                                       │
│  8. 检查能力授权 (capabilities 列表)                                   │
│     ├─ 未授权 → ❌ 拒绝                                              │
│     └─ 已授权 → ✅ 允许推理                                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 16.3 双层验证架构

| 层次 | 组件 | 验证内容 | 语言 |
|------|------|---------|------|
| Layer 1 | `prod/web_service/main.py` | 公钥指纹 + RSA签名 + 有效期 + 能力 | Python |
| Layer 2 | `cpp/runtime/license_checker.cpp` | 公钥指纹 + License 解析 + 缓存 | C++ |

两层均独立实现公钥指纹校验。即使绕过 Python 层直接调用 C++ SO，
SO 内部也会验证公钥指纹。

### 16.4 关键编译参数

| 参数 | 用途 | 示例 |
|------|------|------|
| `TRUSTED_PUBKEY_SHA256` | CMake 变量，注入到 SO 编译 | `cmake -DTRUSTED_PUBKEY_SHA256=a1b2c3...` |
| `TRUSTED_PUBKEY_SHA256` | Docker build arg / 环境变量 | `docker build --build-arg TRUSTED_PUBKEY_SHA256=a1b2c3...` |

### 16.5 指纹计算工具

```bash
# 使用项目内置脚本
python3 scripts/compute_pubkey_fingerprint.py /path/to/pubkey.pem
# 输出：a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890

# 也可使用 openssl 命令行
openssl dgst -sha256 -hex /path/to/pubkey.pem | awk '{print $2}'
```

> ⚠️ **注意**：`compute_pubkey_fingerprint.py` 计算的是 PEM 文件原始字节的
> SHA-256，包括换行符。请确保文件未被编辑器修改换行符格式。

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). All rights reserved.*  
*[agilestar.cn](https://agilestar.cn)*
