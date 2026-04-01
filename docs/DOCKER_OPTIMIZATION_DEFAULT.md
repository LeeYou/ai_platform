# Docker 构建缓存优化 - 默认启用说明

**更新时间**: 2026-03-31
**版本**: v1.7
**提交**: 421da3b

## 变更概述

从 v1.7 开始，Docker 构建缓存优化已作为**默认配置**集成到项目中。用户无需修改任何构建命令即可自动享受优化效果。

## 核心变更

### 1. Dockerfile 替换

```bash
# 旧版（v1.6 及之前）
train/Dockerfile                  # 未优化版本
train/Dockerfile.optimized        # 优化版本（需手动指定）

# 新版（v1.7 开始）
train/Dockerfile                  # 优化版本（默认）
train/Dockerfile.legacy           # 旧版备份（可选回退）
```

**影响**：
- ✅ 所有标准构建命令自动使用优化版 Dockerfile
- ✅ 代码修改后重新构建仅需 30-60 秒（原来 10-15 分钟）
- ✅ 节省 95% 构建时间

### 2. BuildKit 自动启用

**新增文件**：
- `deploy/.env` - Docker Compose 自动读取，启用 BuildKit
- `deploy/.env.example` - 配置示例文件

**内容**：
```bash
DOCKER_BUILDKIT=1
COMPOSE_DOCKER_CLI_BUILD=1
```

**影响**：
- ✅ `docker compose build` 命令自动启用 BuildKit 缓存优化
- ✅ pip 和 npm 下载缓存持久化
- ℹ️  `docker build` 命令仍需手动设置环境变量（运行 `source scripts/enable_buildkit.sh`）

### 3. 自动化脚本增强

**更新文件**：`deploy/mount_template/init_host_dirs.sh`

**新增功能**：
- 自动检测并创建 `deploy/.env` 文件
- 首次初始化时自动配置 BuildKit

**使用**：
```bash
sudo bash deploy/mount_template/init_host_dirs.sh
# 输出：[ai_platform] 已创建 deploy/.env 文件（BuildKit 优化配置）
```

### 4. 文档全面更新

#### `docs/docker_operations_manual.md` (v1.7)

**第 6 节标题变更**：
- 旧：`6. Docker 构建缓存优化（推荐）`
- 新：`6. Docker 构建缓存优化（已默认启用）`

**关键修改**：
- 所有构建命令示例使用标准路径 `train/Dockerfile`
- 新增 6.8 节：回退到旧版 Dockerfile 的方法
- 强调 BuildKit 在 `docker compose` 中自动启用

#### `docs/design/docker_build_cache_optimization.md` (v1.1)

**新增顶部公告**：
```markdown
## 📢 重要更新（v1.1）

从 v1.7 开始，本优化方案已作为默认配置集成到项目中：
1. ✅ train/Dockerfile 已替换为优化版本
2. ✅ deploy/.env 文件已创建
3. ✅ 旧版 Dockerfile 保留为 train/Dockerfile.legacy

用户操作：无需任何修改，直接使用标准构建命令即可
```

## 用户操作指南

### 标准构建流程（无需修改）

```bash
# 1. 构建训练镜像（自动使用优化版）
docker build -t agilestar/ai-train:latest -f train/Dockerfile .

# 或使用 docker compose（推荐，自动启用 BuildKit）
docker compose build train

# 2. 启动服务
docker compose up -d
```

### 首次部署（新环境）

```bash
# 1. 初始化目录结构（自动创建 .env）
sudo bash deploy/mount_template/init_host_dirs.sh

# 2. 启用 BuildKit（可选，docker compose 已自动启用）
source scripts/enable_buildkit.sh

# 3. 构建并启动
cd deploy
docker compose up -d --build
```

### 性能预期

| 场景 | v1.6 及之前 | v1.7（优化默认） | 时间节省 |
|-----|------------|----------------|---------|
| 首次构建 | 10-15 分钟 | 10-15 分钟 | - |
| 修改训练脚本代码 | 10-15 分钟 | **30-60 秒** | **95%** |
| 修改 requirements.txt | 10-15 分钟 | **3-5 分钟** | **70%** |
| 修改前端代码 | 10-15 分钟 | **2-3 分钟** | **80%** |

## 回退方案

如需回退到旧版 Dockerfile（不推荐）：

```bash
# 方法一：使用 legacy Dockerfile
docker build -t agilestar/ai-train:latest -f train/Dockerfile.legacy .

# 方法二：恢复旧版为默认（需要 git 操作）
git mv train/Dockerfile train/Dockerfile.optimized
git mv train/Dockerfile.legacy train/Dockerfile
git commit -m "revert: use legacy Dockerfile as default"
```

## 技术细节

### Dockerfile 优化策略

优化后的 `train/Dockerfile` 采用 5 层依赖分离策略：

```dockerfile
# Level 0: 系统依赖（几乎不变）
RUN apt-get install ...

# Level 1: PyTorch（2GB，很少变）
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch==2.4.1 torchvision==0.19.1

# Level 2: 基础库（偶尔变）
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install numpy opencv-python-headless pillow

# Level 3: 后端依赖（相对稳定）
COPY train/backend/requirements.txt ...
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Level 4: 业务依赖（经常变）
COPY train/scripts/*/requirements.txt ...
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Level 5: 源码（频繁变）
COPY train/ ...
```

**关键原理**：
- 稳定的大依赖在前（PyTorch 2GB），易变的小依赖在后
- 业务依赖修改不会导致 PyTorch 重新下载
- BuildKit 缓存挂载 (`--mount=type=cache`) 使 pip/npm 下载缓存持久化

### BuildKit 缓存机制

```bash
# 启用 BuildKit 后的效果
RUN --mount=type=cache,target=/root/.cache/pip pip install torch
#   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   pip 下载缓存在多次构建间复用，即使层缓存失效
```

## 验证优化效果

```bash
# 1. 首次构建（记录时间）
time docker build -t agilestar/ai-train:latest -f train/Dockerfile .
# 预期：10-15 分钟

# 2. 修改一行代码
echo "# test" >> train/scripts/face_detect/train.py

# 3. 重新构建（记录时间）
time docker build -t agilestar/ai-train:latest -f train/Dockerfile .
# 预期：30-60 秒

# 4. 检查缓存命中情况
docker build -t agilestar/ai-train:latest -f train/Dockerfile . 2>&1 | grep "CACHED"
# 应看到大量 CACHED 层
```

## 常见问题

### Q1: 我的构建还是很慢，怎么办？

**检查清单**：
1. 确认 BuildKit 已启用：`echo $DOCKER_BUILDKIT`（应输出 1）
2. 确认使用正确的 Dockerfile：`docker build -f train/Dockerfile ...`
3. 确认 `.dockerignore` 文件存在：`cat .dockerignore`
4. 清理构建缓存后重试：`docker builder prune -a`

### Q2: .env 文件为什么不在 git 中？

**原因**：`.env` 文件通常包含敏感配置，默认被 `.gitignore` 排除。

**解决**：
- 项目已提供 `.env.example` 文件作为参考
- `init_host_dirs.sh` 脚本会自动创建 `.env` 文件
- 手动创建：`cp deploy/.env.example deploy/.env`

### Q3: 可以只对某个镜像应用优化吗？

**回答**：当前优化已默认应用于 `train/Dockerfile`。其他镜像（license、test、build）暂未优化，但可参考优化策略自行改造。

## 相关文档

- **完整优化指南**：`docs/design/docker_build_cache_optimization.md`
- **操作手册**：`docs/docker_operations_manual.md`（第 6 节）
- **BuildKit 官方文档**：https://docs.docker.com/build/buildkit/

## 变更日志

### v1.7 (2026-03-31)

- ✅ 优化版 Dockerfile 成为默认版本
- ✅ 创建 .env 文件自动启用 BuildKit
- ✅ 更新所有相关文档
- ✅ 旧版 Dockerfile 保留为 .legacy 备份

### v1.6 (2026-03-30)

- 创建优化版 Dockerfile.optimized
- 需手动指定 `-f train/Dockerfile.optimized`
