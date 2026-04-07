# AI 平台部署手册

> **北京爱知之星科技股份有限公司 (Agile Star)**
>
> 版本：1.0 &nbsp;|&nbsp; 最后更新：2025-07

---

## 目录

1. [系统要求](#1-系统要求)
2. [环境准备](#2-环境准备)
3. [宿主机目录初始化](#3-宿主机目录初始化)
4. [开发环境部署](#4-开发环境部署)
5. [生产环境部署](#5-生产环境部署)
6. [服务验证](#6-服务验证)
7. [常见问题排查](#7-常见问题排查)
8. [附录：端口与目录速查表](#8-附录端口与目录速查表)

---

## 1. 系统要求

### 1.1 操作系统

| 项目     | 要求                              |
|----------|-----------------------------------|
| 操作系统 | Ubuntu 22.04 LTS（推荐）或 CentOS 8+ |
| 内核版本 | ≥ 5.4                             |
| 架构     | x86_64（ARM64 仅限编译服务）       |

### 1.2 硬件配置

| 资源     | 最低要求          | 推荐配置            |
|----------|-------------------|---------------------|
| CPU      | 8 核              | 16 核               |
| 内存     | 16 GB             | 32 GB               |
| 磁盘     | 100 GB 可用空间    | 500 GB SSD          |
| GPU      | NVIDIA（训练服务必须） | NVIDIA T4 / A10 或更高 |

> **说明**：生产推理服务（`prod`）可运行在无 GPU 的机器上，但有 GPU 时推理速度将大幅提升。
> 训练服务（`train`）必须使用 NVIDIA GPU。

### 1.3 软件版本

| 软件                      | 最低版本   |
|---------------------------|-----------|
| Docker Engine             | 24.0+     |
| Docker Compose V2 插件     | 2.20+     |
| NVIDIA 驱动               | 525+      |
| NVIDIA Container Toolkit  | 1.14+     |
| CUDA（宿主机驱动层）       | 11.8+     |

---

## 2. 环境准备

> 以下命令均在 **root** 用户或 **sudo** 权限下执行。

### 2.1 安装 Docker Engine

```bash
# 1. 卸载旧版本（如有）
sudo apt-get remove -y docker docker-engine docker.io containerd runc

# 2. 安装依赖
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# 3. 添加 Docker 官方 GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 4. 添加软件源
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. 安装 Docker Engine + Compose 插件
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# 6. 验证安装
docker --version           # 应输出 Docker version 24.x 或更高
docker compose version     # 应输出 Docker Compose version v2.x
```

> ⚠️ **重要**：本项目使用 `docker compose`（V2 插件语法），**不是** `docker-compose`（V1）。
> 所有命令中请使用 `docker compose`，中间是空格。

### 2.2 安装 NVIDIA Container Toolkit（GPU 支持）

如果服务器配有 NVIDIA GPU，需安装 NVIDIA Container Toolkit，使容器内能访问 GPU。

```bash
# 1. 确认宿主机已安装 NVIDIA 驱动
nvidia-smi
# 应能看到 GPU 型号和驱动版本（≥ 525）

# 2. 添加 NVIDIA Container Toolkit 软件源
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L "https://nvidia.github.io/libnvidia-container/${distribution}/libnvidia-container.list" | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 3. 安装
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 4. 配置 Docker 运行时
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 5. 验证 GPU 在容器中可用
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

如果最后一步能正常输出 GPU 信息，则 GPU 环境准备完成。

### 2.3 配置 Docker 镜像加速（可选，国内推荐）

```bash
sudo mkdir -p /etc/docker
cat <<EOF | sudo tee /etc/docker/daemon.json
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://registry.docker-cn.com"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  }
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

---

## 3. 宿主机目录初始化

平台的所有持久化数据（模型、数据集、日志、授权文件等）统一存放在宿主机的 `/data/ai_platform/` 目录下，通过 Docker 卷挂载到各容器中。

### 3.1 执行初始化脚本

```bash
# 进入项目部署目录
cd deploy/mount_template

# 执行初始化脚本（需 root 权限）
sudo bash init_host_dirs.sh
```

默认会在 `/data/ai_platform/` 下创建完整的目录结构。如需自定义根路径，可通过环境变量指定：

```bash
sudo AI_PLATFORM_ROOT=/opt/ai_platform bash init_host_dirs.sh
```

### 3.2 目录结构说明

初始化完成后，将创建以下目录结构：

```
/data/ai_platform/
├── output/                          # 最终交付产物
├── licenses/                        # 授权文件（权限 700）
├── pipelines/                       # AI 流水线配置
│   ├── silent_liveness_check.json   # 静默活体检测流水线
│   └── active_liveness_check.json   # 指令活体检测流水线
├── logs/                            # 各服务日志
│   ├── train/
│   ├── test/
│   ├── build/
│   ├── license/
│   └── prod/
├── datasets/                        # 训练/测试数据集（按能力分目录）
│   ├── face_detect/
│   ├── handwriting_reco/
│   ├── recapture_detect/
│   └── id_card_classify/
├── models/                          # 模型文件（按能力分目录）
│   ├── face_detect/
│   ├── handwriting_reco/
│   ├── recapture_detect/
│   └── id_card_classify/
└── libs/                            # 编译产物（按架构和能力分目录）
    ├── linux_x86_64/
    ├── linux_aarch64/
    └── windows_x86_64/
```

### 3.3 权限说明

| 目录          | 权限  | 说明                              |
|---------------|-------|-----------------------------------|
| `licenses/`   | `700` | 仅 root 可读写，防止授权文件泄露     |
| `datasets/`   | `755` | 训练工具需读写（如样本生成工具）     |
| `logs/`       | `777` | 容器内非 root 用户也需写入日志       |

### 3.4 验证目录

```bash
ls -la /data/ai_platform/
# 确认以上目录均已创建
```

---

## 4. 开发环境部署

开发环境（研发环境）默认包含以下 5 个服务，另可按需启用 1 个 GPU builder：

| 服务     | 容器名            | 端口  | 用途              |
|----------|-------------------|-------|-------------------|
| license  | `ai-license-mgr`  | 8003  | 授权管理           |
| train    | `ai-train`         | 8001  | 模型训练           |
| test     | `ai-test`          | 8002  | 模型测试           |
| build    | `ai-builder`       | 8004  | SDK 编译构建       |
| redis    | `ai-redis`         | 6379（仅本地） | 训练任务消息队列 |

可选 GPU builder（仅在宿主机已配置 NVIDIA Container Toolkit 时启用）：

| 服务      | 容器名            | 端口  | 用途 |
|-----------|-------------------|-------|------|
| build-gpu | `ai-builder-gpu`  | 8007  | 需要 CUDA Toolkit / TensorRT 的编译任务 |

### 4.1 拉取镜像

```bash
cd deploy

docker compose pull
```

> 如果使用离线镜像包，先执行 `docker load -i <镜像包.tar>` 导入。

### 4.2 启动全部服务

```bash
cd deploy

# 后台启动所有服务
docker compose up -d
```

如需启用 GPU builder：

```bash
docker compose --profile gpu-build up -d --build build-gpu
```

### 4.3 查看启动状态

```bash
docker compose ps
```

正常情况下所有服务状态应为 `Up` 且健康状态为 `(healthy)`：

```
NAME              STATUS              PORTS
ai-license-mgr   Up (healthy)        0.0.0.0:8003->8003/tcp
ai-train          Up (healthy)        0.0.0.0:8001->8001/tcp
ai-test           Up (healthy)        0.0.0.0:8002->8002/tcp
ai-builder        Up (healthy)        0.0.0.0:8004->8004/tcp
ai-redis          Up (healthy)        127.0.0.1:6379->6379/tcp
```

如果启用了 GPU builder，还会看到：

```text
ai-builder-gpu    Up (healthy)        0.0.0.0:8007->8004/tcp
```

### 4.4 查看服务日志

```bash
# 查看所有服务日志（实时跟踪）
docker compose logs -f

# 只看某个服务的日志
docker compose logs -f train

# 查看最近 100 行日志
docker compose logs --tail 100 train
```

### 4.5 GPU builder 启动前核查

```bash
# 1. 宿主机驱动
nvidia-smi

# 2. Docker GPU runtime
docker run --rm --gpus all \
  nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 \
  nvidia-smi

# 3. 启动 GPU builder
docker compose --profile gpu-build up -d --build build-gpu

# 4. 查看 builder 诊断
curl http://localhost:8007/api/v1/builder/diagnostics
```

### 4.6 编译期 GPU 开关说明

- 运行时 GPU 优先/CPU 回退能力：**无需**传 `-DBUILD_GPU=ON`
- 只有在能力源码确实需要编译期依赖时才开启：
  - `-DENABLE_TENSORRT=ON`
  - `-DENABLE_CUDA_KERNELS=ON`
- Build Web 页面已提供独立“编译期 GPU 开关”，会根据当前 builder 诊断自动禁用不可用选项

### 4.7 停止服务

```bash
# 停止所有服务（保留数据卷）
docker compose down

# 停止并删除数据卷（⚠️ Redis 数据将丢失）
docker compose down -v
```

### 4.8 重启单个服务

```bash
docker compose restart train
```

### 4.9 更新镜像并重启

```bash
docker compose pull
docker compose up -d
```

Docker Compose 会自动检测镜像变化，仅重建需要更新的容器。

---

## 5. 生产环境部署

生产环境为单容器部署，仅包含推理服务。

| 服务 | 容器名     | 端口 | 用途         |
|------|-----------|------|-------------|
| prod | `ai-prod` | 8080 | 生产推理服务 |

### 5.1 前置条件

在部署生产环境之前，确保：

1. ✅ 宿主机目录已初始化（[第 3 节](#3-宿主机目录初始化)）
2. ✅ `/data/ai_platform/models/` 下已放置训练好的模型文件
3. ✅ `/data/ai_platform/libs/` 下已放置编译好的 SDK 库文件
4. ✅ `/data/ai_platform/licenses/` 下已放置有效的授权文件

### 5.2 配置环境变量

生产环境支持通过环境变量自定义行为。在启动前设置：

```bash
# 管理员令牌（必须修改！不要使用默认值）
export AI_ADMIN_TOKEN="your-strong-random-token-here"

# 最大并发推理实例数（默认 4，根据 GPU 显存调整）
export AI_MAX_INSTANCES=4

# 推理资源获取超时秒数（默认 30）
export AI_ACQUIRE_TIMEOUT_S=30

# 目标架构（默认 linux_x86_64）
export AI_ARCH=linux_x86_64
```

> ⚠️ **安全警告**：`AI_ADMIN_TOKEN` 默认值为 `changeme`，**必须**在生产环境中修改为高强度随机字符串。

也可以创建 `.env` 文件放在 `deploy/` 目录下：

```bash
cat > deploy/.env <<'EOF'
AI_ADMIN_TOKEN=your-strong-random-token-here
AI_MAX_INSTANCES=4
AI_ACQUIRE_TIMEOUT_S=30
AI_ARCH=linux_x86_64
EOF
```

### 5.3 启动生产服务

```bash
cd deploy

# 使用生产 compose 文件启动
docker compose -f docker-compose.prod.yml up -d
```

### 5.4 查看运行状态

```bash
docker compose -f docker-compose.prod.yml ps
```

期望输出：

```
NAME       STATUS              PORTS
ai-prod    Up (healthy)        0.0.0.0:8080->8080/tcp
```

### 5.5 查看生产日志

```bash
# 实时查看日志
docker compose -f docker-compose.prod.yml logs -f prod

# 也可查看宿主机上的日志文件
tail -f /data/ai_platform/logs/prod/*.log
```

### 5.6 停止生产服务

```bash
docker compose -f docker-compose.prod.yml down
```

### 5.7 更新生产镜像

```bash
cd deploy

# 拉取最新镜像
docker compose -f docker-compose.prod.yml pull

# 重新启动（自动替换旧容器）
docker compose -f docker-compose.prod.yml up -d
```

### 5.8 无 GPU 环境部署

如果生产服务器没有 NVIDIA GPU，需要注释掉 `docker-compose.prod.yml` 中的 GPU 配置段：

```yaml
# deploy:
#   resources:
#     reservations:
#       devices:
#         - driver: nvidia
#           count: all
#           capabilities: [gpu]
```

然后正常启动即可，服务将以 CPU 模式运行推理。

---

## 6. 服务验证

### 6.1 开发环境健康检查

逐一检查各服务的健康状态端点：

```bash
# 授权管理服务
curl -f http://localhost:8003/health
# 期望返回: {"status":"ok"} 或 HTTP 200

# 训练服务
curl -f http://localhost:8001/health
# 期望返回: {"status":"ok"} 或 HTTP 200

# 测试服务
curl -f http://localhost:8002/health
# 期望返回: {"status":"ok"} 或 HTTP 200

# 编译构建服务
curl -f http://localhost:8004/health
# 期望返回: {"status":"ok"} 或 HTTP 200

# Redis（仅限本机）
docker exec ai-redis redis-cli ping
# 期望返回: PONG
```

### 6.2 生产环境健康检查

```bash
# 生产推理服务
curl -f http://localhost:8080/api/v1/health
# 期望返回: {"status":"ok"} 或 HTTP 200
```

### 6.3 批量验证脚本

以下一键脚本可同时验证所有开发环境服务：

```bash
#!/bin/bash
echo "=== AI 平台服务状态检查 ==="

services=(
  "授权管理 (license)|http://localhost:8003/health"
  "模型训练 (train)|http://localhost:8001/health"
  "模型测试 (test)|http://localhost:8002/health"
  "SDK 构建 (build)|http://localhost:8004/health"
)

for svc in "${services[@]}"; do
  name="${svc%%|*}"
  url="${svc##*|}"
  if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
    echo "  ✅ $name — 正常"
  else
    echo "  ❌ $name — 异常"
  fi
done

# Redis 单独检查
if docker exec ai-redis redis-cli ping 2>/dev/null | grep -q PONG; then
  echo "  ✅ Redis — 正常"
else
  echo "  ❌ Redis — 异常"
fi
echo "=== 检查完毕 ==="
```

### 6.4 Docker 容器健康状态

```bash
# 查看容器内置健康检查结果
docker inspect --format='{{.Name}} {{.State.Health.Status}}' \
  ai-license-mgr ai-train ai-test ai-builder ai-redis
```

---

## 7. 常见问题排查

### 7.1 容器启动失败

**现象**：`docker compose ps` 显示容器状态为 `Restarting` 或 `Exit`。

**排查步骤**：

```bash
# 查看容器日志
docker compose logs <服务名>

# 查看容器退出原因
docker inspect --format='{{.State.ExitCode}} {{.State.Error}}' <容器名>
```

**常见原因**：
- 端口被占用 → 用 `ss -tlnp | grep <端口号>` 排查，停止占用进程
- 挂载目录不存在 → 重新运行 `init_host_dirs.sh`
- 镜像不存在 → 执行 `docker compose pull` 拉取

### 7.2 GPU 不可用

**现象**：`train` 服务日志报 GPU 相关错误。

**排查步骤**：

```bash
# 1. 确认宿主机 GPU 驱动正常
nvidia-smi

# 2. 确认 NVIDIA Container Toolkit 已安装
nvidia-ctk --version

# 3. 确认 Docker 可以访问 GPU
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# 4. 确认 Docker 运行时配置
cat /etc/docker/daemon.json
# 应包含 "nvidia" 运行时配置
```

**解决方案**：
- 驱动未安装 → 安装 NVIDIA 驱动 525+
- toolkit 未配置 → 重新执行 [2.2 节](#22-安装-nvidia-container-toolkitgpu-支持)
- 配置变更后 → `sudo systemctl restart docker`

### 7.3 磁盘空间不足

**现象**：服务运行一段时间后容器异常退出。

**排查步骤**：

```bash
# 查看磁盘使用情况
df -h /data

# 查看 Docker 磁盘占用
docker system df

# 清理无用的 Docker 资源（已停止的容器、悬空镜像等）
docker system prune -f

# 清理未使用的镜像
docker image prune -a -f
```

### 7.4 Redis 连接失败

**现象**：`train` 服务日志报 `ConnectionError: Error connecting to redis://redis:6379`。

**排查步骤**：

```bash
# 确认 Redis 容器正在运行
docker compose ps redis

# 从 train 容器内测试连接
docker exec ai-train bash -c "python -c \"import redis; r=redis.Redis(host='redis'); print(r.ping())\""

# 查看 Redis 日志
docker compose logs redis
```

**解决方案**：
- Redis 未启动 → `docker compose up -d redis`
- Redis 内存不足 → 检查 `docker stats ai-redis` 的内存占用

### 7.5 服务健康检查持续失败

**现象**：`docker compose ps` 显示 `(unhealthy)`。

**排查步骤**：

```bash
# 查看健康检查详细信息
docker inspect --format='{{json .State.Health}}' <容器名> | python3 -m json.tool

# 手动执行健康检查命令
docker exec <容器名> curl -f http://localhost:<端口>/health
```

**常见原因**：
- 服务仍在启动中 → 等待 start_period 时间（通常 15–30 秒）
- 应用内部错误 → 查看容器日志排查

### 7.6 容器内时间不正确

**现象**：日志时间戳与实际时间不一致。

**排查**：

```bash
docker exec <容器名> date
```

所有容器已配置 `TZ=Asia/Shanghai`。如果宿主机时间本身不对，先校正宿主机时间：

```bash
sudo timedatectl set-timezone Asia/Shanghai
sudo timedatectl set-ntp true
```

### 7.7 授权文件无法识别

**现象**：`build` 服务报授权错误。

**排查步骤**：

```bash
# 确认授权文件已放入正确目录
ls -la /data/ai_platform/licenses/

# 确认 license 服务已正常运行
curl -f http://localhost:8003/health

# 查看 build 服务与 license 服务的通信日志
docker compose logs build | grep -i license
```

---

## 8. 附录：端口与目录速查表

### 端口分配

| 端口 | 环境   | 服务     | 说明             |
|------|--------|----------|------------------|
| 8001 | 开发   | train    | 模型训练 API     |
| 8002 | 开发   | test     | 模型测试 API     |
| 8003 | 开发   | license  | 授权管理 API     |
| 8004 | 开发   | build    | SDK 编译构建 API |
| 6379 | 开发   | redis    | 消息队列（仅本地） |
| 8080 | 生产   | prod     | 推理服务 API     |

### 宿主机挂载目录

| 宿主机路径                          | 容器内路径                 | 服务          | 读写 |
|------------------------------------|---------------------------|--------------|------|
| `/data/ai_platform/licenses`       | `/data/licenses`          | license      | rw   |
| `/data/ai_platform/licenses`       | `/mnt/ai_platform/licenses` | prod       | ro   |
| `/data/ai_platform/datasets`       | `/workspace/datasets`     | train (rw), test (ro) | —  |
| `/data/ai_platform/models`         | `/workspace/models`       | train (rw), test (ro) | —  |
| `/data/ai_platform/models`         | `/mnt/ai_platform/models` | prod         | ro   |
| `/data/ai_platform/libs/linux_x86_64` | `/workspace/libs/linux_x86_64` | build | rw   |
| `/data/ai_platform/libs/${AI_ARCH}` | `/mnt/ai_platform/libs`  | prod         | ro   |
| `/data/ai_platform/pipelines`      | `/mnt/ai_platform/pipelines` | prod      | rw   |
| `/data/ai_platform/logs/<服务名>`   | 各服务日志目录             | 所有         | rw   |

### Docker Compose 命令速查

```bash
# ——— 开发环境（在 deploy/ 目录下执行）———
docker compose up -d                # 启动所有服务
docker compose down                 # 停止所有服务
docker compose ps                   # 查看状态
docker compose logs -f <服务名>      # 查看日志
docker compose restart <服务名>      # 重启服务
docker compose pull                 # 拉取最新镜像

# ——— 生产环境（在 deploy/ 目录下执行）———
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f prod
docker compose -f docker-compose.prod.yml pull
```
