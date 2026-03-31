# Docker 构建缓存优化方案

**北京爱知之星科技股份有限公司 (Agile Star)**
**版本:** v1.1 | **日期:** 2026-03-31 | **文档编号:** OPT-DOCKER-001
**官网：[agilestar.cn](https://agilestar.cn)**

---

## 📢 重要更新（v1.1）

**从 v1.7 开始，本优化方案已作为默认配置集成到项目中：**

1. ✅ **train/Dockerfile 已替换为优化版本** - 无需使用 `-f train/Dockerfile.optimized`
2. ✅ **deploy/.env 文件已创建** - `docker compose` 命令自动启用 BuildKit
3. ✅ **旧版 Dockerfile 保留为 train/Dockerfile.legacy** - 可选回退

**用户操作**：无需任何修改，直接使用标准构建命令即可享受优化效果：
```bash
# 标准命令（已自动使用优化版）
docker build -t agilestar/ai-train:latest -f train/Dockerfile .
docker compose build train
```

**本文档内容**：以下内容详细说明了优化的原理、实现细节和最佳实践，供深入了解和问题排查使用。

---

## 1. 问题分析

### 1.1 现状描述

当前训练镜像（train/Dockerfile）每次构建时会重复下载大量依赖：
- PyTorch: ~2.0 GB
- CUDA工具链: 包含在基础镜像中 ~5 GB
- 其他Python包: ~500 MB
- npm包: ~200 MB

**总下载量：每次构建约 7-8 GB**

### 1.2 根本原因

**Docker 层缓存失效机制**：
1. 当 Dockerfile 中某一行的输入（COPY的文件内容、RUN的命令）发生变化时，该层及其后续所有层的缓存都会失效
2. 在同一个 RUN 命令中安装多个包时，任何一个包的版本变化都会导致整个命令重新执行

**具体案例 - train/Dockerfile 第76-82行**：
```dockerfile
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cu118 \
    && pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r train/scripts/face_detect/requirements.txt \
    -r train/scripts/desktop_recapture_detect/requirements.txt \
    && python3 -c "import torch; ..."
```

**问题**：如果 `face_detect/requirements.txt` 中的 `ultralytics` 从 8.1.0 升级到 8.2.0，整个 RUN 命令会重新执行，包括重新下载 2GB 的 PyTorch！

---

## 2. 优化策略

### 2.1 核心原则

1. **依赖分层**：将稳定的大型依赖和易变的小依赖分开安装
2. **COPY 最小化**：只 COPY 当前步骤需要的文件
3. **顺序优化**：稳定的层在前，易变的层在后
4. **多阶段构建**：分离构建和运行时依赖

### 2.2 依赖稳定性分级

| 级别 | 依赖类型 | 更新频率 | 示例 | 大小 |
|------|---------|---------|------|------|
| **Level 0** | 基础镜像 | 几乎不变 | nvidia/cuda:11.8.0 | 5 GB |
| **Level 1** | 核心框架 | 很少变 | torch, torchvision | 2 GB |
| **Level 2** | 框架基础库 | 偶尔变 | numpy, opencv, pillow | 300 MB |
| **Level 3** | 业务依赖 | 经常变 | ultralytics, onnxslim | 200 MB |
| **Level 4** | 应用代码 | 频繁变 | train/backend/*.py | 10 MB |

---

## 3. 具体优化方案

### 3.1 训练镜像优化（train/Dockerfile）

#### 方案A：多层分离安装（推荐）

```dockerfile
# =============================================================================
# 优化后的 train/Dockerfile
# =============================================================================

FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# Level 0: 系统依赖（很少变化）
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-dev python3-pip \
    curl ca-certificates \
    libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

# ---------------------------------------------------------------------------
# Level 1: 核心框架（PyTorch - 2GB，几乎不会变）
# 🔑 关键优化：单独一层安装 PyTorch，与业务依赖隔离
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir \
    torch==2.4.1 torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cu118

# ---------------------------------------------------------------------------
# Level 2: 框架基础库（偶尔变化）
# 🔑 关键优化：numpy、opencv 等基础库单独一层
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    numpy>=1.24.0 \
    opencv-python-headless>=4.8.0 \
    Pillow>=10.0.0 \
    pyyaml>=6.0 \
    tqdm>=4.65.0

# ---------------------------------------------------------------------------
# Level 2.5: FastAPI 后端依赖（稳定）
# ---------------------------------------------------------------------------
COPY train/backend/requirements.txt train/backend/requirements.txt
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r train/backend/requirements.txt

# ---------------------------------------------------------------------------
# Level 3: 业务特定依赖（经常变化）
# 🔑 关键优化：ultralytics 等业务依赖单独安装，不影响 PyTorch 层
# ---------------------------------------------------------------------------
COPY train/scripts/face_detect/requirements.txt /tmp/face_detect_req.txt
COPY train/scripts/desktop_recapture_detect/requirements.txt /tmp/desktop_req.txt

RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r /tmp/face_detect_req.txt \
    -r /tmp/desktop_req.txt \
    && python3 -c "import torch; import cv2; from PIL import Image; print(f'[OK] PyTorch {torch.__version__} CUDA {torch.version.cuda}')"

# ---------------------------------------------------------------------------
# Level 4: 前端构建（Node模块）
# ---------------------------------------------------------------------------
COPY train/frontend/package*.json train/frontend/
RUN cd train/frontend \
    && npm config set registry https://registry.npmmirror.com \
    && npm install

COPY train/frontend/ train/frontend/
RUN cd train/frontend && npm run build

# ---------------------------------------------------------------------------
# Level 5: 应用代码（最频繁变化）
# ---------------------------------------------------------------------------
COPY train/scripts/ train/scripts/
COPY train/backend/ train/backend/

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    DATASETS_ROOT=/workspace/datasets \
    MODELS_ROOT=/workspace/models \
    REDIS_URL=redis://redis:6379/0

RUN mkdir -p /workspace/logs

EXPOSE 8001

WORKDIR /app/train/backend

CMD ["sh", "-c", \
    "celery -A tasks.celery_app worker --loglevel=info --detach && \
     uvicorn main:app --host 0.0.0.0 --port 8001"]
```

#### 优化效果对比

| 变更场景 | 优化前重新下载 | 优化后重新下载 | 节省 |
|---------|--------------|--------------|------|
| **更新业务代码** | 7-8 GB | 0 MB | 100% |
| **更新 ultralytics** | 2.5 GB (PyTorch + deps) | 200 MB | 92% |
| **更新 numpy 版本** | 2.5 GB | 300 MB | 88% |
| **更新 PyTorch** | 2.5 GB | 2.0 GB | 20% |

### 3.2 进一步优化：BuildKit 缓存挂载

使用 Docker BuildKit 的 `--mount=type=cache` 特性：

```dockerfile
# 在 RUN pip install 前加上缓存挂载
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    torch==2.4.1 torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cu118
```

**启用方式**：
```bash
# 设置环境变量
export DOCKER_BUILDKIT=1

# 或在 docker-compose.yml 中
DOCKER_BUILDKIT=1 docker compose build
```

**效果**：即使层缓存失效，pip 也会从本地缓存读取已下载的包，避免网络下载。

---

## 4. 基础镜像优化

### 4.1 使用精简的运行时镜像

**问题**：`nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04` 包含完整的开发工具（gcc、nvcc等），对于运行时不需要。

**优化**：使用多阶段构建

```dockerfile
# Stage 1: 完整开发环境（仅用于编译扩展）
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04 AS builder

# 安装 PyTorch 和可能需要编译的包
RUN pip install torch torchvision ...

# Stage 2: 精简运行时
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# 只复制需要的文件
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
```

**节省**：基础镜像从 5GB 减少到 3GB

### 4.2 自定义基础镜像（高级）

为整个项目创建一个基础镜像，预装稳定依赖：

```dockerfile
# base-images/ai-train-base.Dockerfile
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# 安装系统依赖 + PyTorch + 基础库
RUN apt-get update && apt-get install -y python3.10 ...
RUN pip install torch==2.4.1 torchvision==0.19.1 numpy opencv-python ...

# 构建并推送到私有仓库
# docker build -t agilestar/ai-train-base:cuda11.8-torch2.4 .
# docker push agilestar/ai-train-base:cuda11.8-torch2.4
```

然后在 train/Dockerfile 中：
```dockerfile
FROM agilestar/ai-train-base:cuda11.8-torch2.4

# 只安装业务依赖
COPY train/scripts/*/requirements.txt /tmp/
RUN pip install -r /tmp/face_detect_req.txt ...
```

**优势**：
- 基础镜像可以预先构建并缓存在本地/私有仓库
- 日常开发只需下载业务依赖（~200MB）

---

## 5. npm 依赖优化

### 5.1 package-lock.json 锁定版本

确保所有前端项目都有 `package-lock.json`：

```dockerfile
# 只 COPY package*.json，利用层缓存
COPY train/frontend/package*.json train/frontend/
RUN cd train/frontend && npm ci  # 使用 npm ci 而不是 npm install

# 然后再 COPY 源代码
COPY train/frontend/ train/frontend/
RUN cd train/frontend && npm run build
```

### 5.2 npm 缓存挂载

```dockerfile
RUN --mount=type=cache,target=/root/.npm \
    cd train/frontend && npm ci
```

---

## 6. 实施步骤

### 6.1 立即可做（低风险）

1. **拆分 pip install 命令**（见方案A）
   - 修改 `train/Dockerfile` 第76-82行
   - 预期节省：90%+ 的重复下载

2. **启用 BuildKit 缓存**
   ```bash
   echo 'export DOCKER_BUILDKIT=1' >> ~/.bashrc
   ```

3. **添加 .dockerignore**
   ```
   # .dockerignore
   **/__pycache__
   **/.git
   **/.vscode
   **/node_modules
   **/.pytest_cache
   **/*.pyc
   **/.DS_Store
   ```

### 6.2 中期优化（需要测试）

1. **创建自定义基础镜像**
   - 预装 PyTorch + CUDA + 基础库
   - 推送到 Docker Hub 或私有仓库

2. **多阶段构建**
   - 分离 devel 和 runtime 镜像

### 6.3 长期优化（可选）

1. **搭建私有 PyPI 镜像**
   - 使用 devpi 或 Nexus
   - 缓存所有下载过的包

2. **CI/CD 缓存优化**
   - GitHub Actions: 使用 `actions/cache`
   - GitLab CI: 使用 `cache` 配置

---

## 7. 监控与验证

### 7.1 构建时间对比

```bash
# 优化前
time docker compose build train
# 预期：首次 30-40 分钟，代码变更后仍需 15-20 分钟

# 优化后
time docker compose build train
# 预期：首次 30-40 分钟，代码变更后仅需 1-2 分钟
```

### 7.2 缓存命中率

```bash
# 查看构建日志中的缓存命中
docker compose build train 2>&1 | grep "Using cache"
```

---

## 8. 最佳实践总结

### ✅ DO（推荐做法）

1. **依赖分层安装**：稳定的大依赖单独一层
2. **锁定版本号**：避免隐式更新导致缓存失效
3. **最小化 COPY**：只在需要时才 COPY 文件
4. **启用 BuildKit**：使用缓存挂载特性
5. **监控构建时间**：持续优化

### ❌ DON'T（避免做法）

1. **不要在一个 RUN 中混装稳定和不稳定依赖**
2. **不要在依赖安装前 COPY 所有代码**
3. **不要使用 `pip install --upgrade` 自动升级**
4. **不要忽略 .dockerignore**
5. **不要在生产镜像中保留开发工具**

---

## 9. 故障排查

### 9.1 缓存未命中

**症状**：明明代码没变，但仍然重新安装依赖

**原因**：
1. requirements.txt 中有版本范围（如 `numpy>=1.24`），每次解析到不同版本
2. COPY 的目录中有隐藏文件变化（如 `.git/`）
3. 系统时间不一致

**解决**：
1. 锁定所有版本号：`pip freeze > requirements.txt`
2. 使用 `.dockerignore` 排除无关文件
3. 使用 `--no-cache-dir` 避免时间戳问题

### 9.2 BuildKit 缓存问题

```bash
# 清理 BuildKit 缓存
docker builder prune

# 禁用缓存重新构建
docker compose build --no-cache train
```

---

## 10. 附录：完整优化示例

详见仓库中的优化版本：
- `train/Dockerfile.optimized`（优化版训练镜像）
- `base-images/ai-train-base.Dockerfile`（自定义基础镜像）

---

**文档维护**: 技术架构组
**联系方式**: tech@agilestar.cn
