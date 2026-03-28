# Docker 镜像与容器构建管理手册

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-28**  
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
13. [故障排查指南](#13-故障排查指南)
14. [附录：端口分配表](#14-附录端口分配表)

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
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 2.4 配置 Docker 日志驱动（推荐）

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
| 2 | `agilestar/ai-train` | `train/Dockerfile` | `nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04` | 8001 | GPU 训练服务 |
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

**基础镜像**：`nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04`

**暴露端口**：8001

**依赖服务**：Redis（作为 Celery 异步任务队列的 broker）

#### 构建命令

```bash
# 标准构建（较大，约 8-12 GB，含 CUDA + cuDNN）
docker build -t agilestar/ai-train:latest -f train/Dockerfile .

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

**用途**：提供 C++ 编译环境，将 AI 能力插件编译为 SO 动态库（Linux x86_64 平台）。

**Dockerfile 路径**：`build/Dockerfile.linux_x86`

**基础镜像**：`ubuntu:22.04`

**暴露端口**：8004

**内含工具**：GCC 12、CMake、Ninja、OpenSSL、ONNXRuntime 1.18.1

#### 构建命令

```bash
# 标准构建
docker build -t agilestar/ai-builder-linux-x86:latest -f build/Dockerfile.linux_x86 .

# 指定版本号
docker build -t agilestar/ai-builder-linux-x86:1.0.0 -f build/Dockerfile.linux_x86 .

# 无缓存构建
docker build --no-cache -t agilestar/ai-builder-linux-x86:latest -f build/Dockerfile.linux_x86 .
```

#### 独立运行

```bash
# 启动编译服务容器
docker run -d \
  --name ai-builder \
  -p 8004:8004 \
  -v /data/ai_platform/libs/linux_x86_64:/output/libs:rw \
  -v /data/ai_platform/logs/build:/workspace/logs:rw \
  -e TZ=Asia/Shanghai \
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
  -v /data/ai_platform/libs/linux_x86_64:/output/libs:rw \
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
```

---

### 5.6 生产推理镜像 (ai-prod)

**用途**：生产环境 AI 推理服务，提供 REST API 接口，支持 GPU/CPU 自适应、实例池并发调度、热重载。

**Dockerfile 路径**：`prod/Dockerfile`

**基础镜像**：`ubuntu:22.04`

**暴露端口**：8080

**入口脚本**：`docker-entrypoint.sh`（自动检测 GPU 并配置推理后端）

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
```

---

## 7. 生产环境启停管理 (docker-compose.prod)

生产环境使用 `deploy/docker-compose.prod.yml`，仅包含生产推理服务。

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
| 编译 | `./data/build_logs/build_service.log` | （需额外挂载） | 50MB × 5 |
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

### 9.2 批量健康检查脚本

```bash
#!/bin/bash
# 保存为 /data/ai_platform/check_health.sh

echo "=== AI Platform Health Check ==="
echo "Time: $(date)"
echo ""

services=(
  "License|http://localhost:8003/health"
  "Train|http://localhost:8001/health"
  "Test|http://localhost:8002/health"
  "Build|http://localhost:8004/health"
  "Prod|http://localhost:8080/api/v1/health"
)

for entry in "${services[@]}"; do
  IFS='|' read -r name url <<< "$entry"
  if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
    echo "  ✅ $name ($url) — healthy"
  else
    echo "  ❌ $name ($url) — unreachable"
  fi
done
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

```
delivery_package/
├── docker/
│   └── agilestar-ai-prod-linux-x86_64-v1.0.0.tar.gz   # 生产镜像
├── docs/
│   ├── ai_capability_market_overview.md                 # AI 能力超市总览
│   ├── docker_operations_manual.md                      # 本手册
│   └── design/                                          # 设计文档
├── sdk_linux_x86_64/include/agilestar/                  # C/C++ SDK 头文件
├── tools/
│   └── license_tool                                     # 机器指纹采集工具
├── mount_template/
│   ├── init_host_dirs.sh                                # 宿主机目录初始化脚本
│   └── README.md
└── DELIVERY_MANIFEST.txt                                # 交付清单和部署说明
```

### 11.3 客户端部署步骤

> **部署模式：通用镜像 + 运行时挂载**
>
> 生产镜像不包含任何客户特定内容。公钥、授权文件、模型、SO 插件均通过
> 宿主机目录挂载注入。一个镜像可服务所有客户。

```bash
# 1. 初始化宿主机目录
sudo bash mount_template/init_host_dirs.sh

# 2. 导入 Docker 镜像（通用镜像，不含客户数据）
docker load < docker/agilestar-ai-prod-linux-x86_64-v1.0.0.tar.gz

# 3. 放置客户公钥（一客户一密钥对，公钥用于运行时签名验证）
sudo cp pubkey.pem /data/ai_platform/licenses/

# 4. 放置 License 文件（用该客户密钥对的私钥签名生成）
sudo cp license.bin /data/ai_platform/licenses/

# 5. 放置模型包
cp -r models/* /data/ai_platform/models/

# 6. 放置 SO 插件（如有）
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
  agilestar/ai-prod:1.0.0

# 8. 验证
curl http://localhost:8080/api/v1/health
curl http://localhost:8080/api/v1/license/status
```

### 11.4 授权密钥对管理（一客户一密钥对）

平台采用 **一客户一密钥对** 管理模式：

| 概念 | 说明 |
|------|------|
| 密钥对粒度 | 每个客户分配一个独立的 RSA-2048 密钥对 |
| 私钥存储 | 仅存于内部授权管理服务器磁盘（`0o600` 权限），数据库中不存储 |
| 公钥存储 | 存于授权管理 DB（`key_pairs` 表），同时交付给客户 |
| License 签名 | 使用客户对应密钥对的私钥签名，`license_records` 表记录 `key_pair_id` |
| 运行时验证 | 生产容器启动时加载挂载的 `pubkey.pem`，对 `license.bin` 做 RSA-PSS SHA256 签名验证 |

**交付给客户的文件（运行时挂载到 `/data/ai_platform/licenses/`）：**

```
/data/ai_platform/licenses/
├── pubkey.pem     ← 该客户密钥对的公钥（用于签名验证）
└── license.bin    ← 该客户的授权文件（包含 capabilities、有效期等）
```

**操作流程：**

```bash
# 1. 在授权管理平台创建客户专属密钥对
#    前端：🔑 密钥管理 → 生成新密钥对
#    名称建议：customer-<客户简称>-<年份>，如 customer-huawei-2026
#    私钥路径：/data/ai_platform/keys/<客户简称>/private_key.pem

# 2. 下载该客户的公钥 PEM（前端"下载公钥"按钮）

# 3. 生成授权时选择该客户的密钥对
#    前端：➕ 生成授权 → 步骤二"签名密钥对"下拉框选择对应密钥

# 4. 将公钥和授权文件一起交付给客户
#    客户部署时放入 /data/ai_platform/licenses/ 目录
```

**密钥轮换：**

```bash
# 如需轮换密钥（如疑似泄露），只需：
# 1. 生成新密钥对（旧密钥对可标记为"停用"）
# 2. 用新密钥对重新签发授权
# 3. 将新的 pubkey.pem + license.bin 交付给客户
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

## 13. 故障排查指南

### 13.1 容器无法启动

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
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
# → 检查 NVIDIA 驱动和 Container Toolkit
```

### 13.2 服务健康检查失败

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

### 13.3 推理返回错误

```bash
# 错误码 4002：License 已过期
# → 更新 License 文件到 /data/ai_platform/licenses/
curl http://localhost:8080/api/v1/license/status

# 错误码 4003：能力未授权
# → 检查 License 中授权的能力列表
curl http://localhost:8080/api/v1/capabilities

# 错误码 4004：机器指纹不匹配
# → 重新为当前服务器生成 License

# 错误码 5002：模型加载失败
# → 检查模型文件是否存在且完整
ls -la /data/ai_platform/models/<capability>/<version>/
docker exec ai-prod ls -la /mnt/ai_platform/models/

# 错误码 5001：推理内部错误
# → 查看详细日志
docker logs --tail 100 ai-prod
tail -50 /data/ai_platform/logs/prod/prod.log
```

### 13.4 GPU 相关问题

```bash
# 检查宿主机 GPU 状态
nvidia-smi

# 检查 Docker GPU 支持
docker info | grep -i nvidia

# 测试 GPU 容器
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# 容器内检查 GPU
docker exec ai-prod nvidia-smi
docker exec ai-train python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# NVIDIA Container Toolkit 未安装
# → 参考第 2.3 节安装步骤
```

### 13.5 磁盘空间不足

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

### 13.6 训练服务 Celery Worker 异常

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

### 13.7 网络连接问题

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

---

## 14. 附录：端口分配表

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

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). All rights reserved.*  
*[agilestar.cn](https://agilestar.cn)*
