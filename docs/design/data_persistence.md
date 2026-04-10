# AI 能力平台 —— 数据持久化架构设计

**北京爱知之星科技股份有限公司 (Agile Star)**
**版本:** v1.1 | **日期:** 2026-04-10 | **文档编号:** ARCH-DATA-001
**官网：[agilestar.cn](https://agilestar.cn)**

---

## 1. 概述

### 1.1 设计目标

- **数据安全**：所有持久化数据存储在宿主机，容器重建不丢失
- **易于备份**：统一的数据目录结构，便于整体备份和迁移
- **可追溯性**：保留所有训练任务、能力配置、授权记录等历史数据
- **高可用性**：支持数据目录迁移到其他服务器，快速恢复服务

### 1.2 核心原则

1. **所有持久化数据必须存储在宿主机** `/data/ai_platform/` 目录
2. **禁止使用 Docker 匿名卷和命名卷**（除非明确用于临时缓存）
3. **数据库文件统一放置在** `/data/ai_platform/data/` 子目录
4. **容器内路径与宿主机路径明确映射**，避免隐式存储

---

## 2. 数据目录结构

### 2.1 宿主机目录树

```
/data/ai_platform/                # 平台根目录
│
├── data/                         # 持久化数据根目录（数据库、配置等）
│   ├── train/                   # 训练服务数据
│   │   └── train.db            # 训练任务、能力配置、标注项目数据库
│   ├── license/                 # 授权服务数据
│   │   └── license.db          # 客户授权记录数据库
│   └── redis/                   # Redis 持久化数据
│       ├── appendonly.aof      # AOF 持久化文件
│       └── dump.rdb            # RDB 快照文件（如启用）
│
├── datasets/                     # 训练数据集
│   ├── face_detect/            # 人脸检测数据集（WIDER FACE 等）
│   ├── handwriting_reco/       # 手写识别数据集
│   ├── recapture_detect/       # 翻拍检测数据集
│   └── id_card_classify/       # 证件分类数据集
│
├── models/                       # 训练产出的模型文件
│   ├── face_detect/
│   │   ├── 1.0.0/
│   │   │   ├── best.pt        # PyTorch 权重
│   │   │   ├── model.onnx     # ONNX 模型
│   │   │   └── checkpoints/   # 训练检查点
│   │   └── 1.1.0/
│   └── handwriting_reco/
│
├── libs/                         # 编译产出的推理库
│   ├── linux_x86_64/
│   │   ├── face_detect/
│   │   │   └── libai_runtime_customer123.so
│   │   └── handwriting_reco/
│   ├── linux_aarch64/
│   └── windows_x86_64/
│
├── licenses/                     # 客户授权文件（license.bin）
│   ├── customer_001/
│   │   └── license.bin
│   └── customer_002/
│
├── logs/                         # 服务日志
│   ├── train/                   # 训练服务日志
│   ├── test/                    # 测试服务日志
│   ├── license/                 # 授权服务日志
│   ├── build/                   # 编译服务日志
│   └── prod/                    # 生产服务日志
│
├── pipelines/                    # Pipeline 配置文件
│   └── default.json
│
└── output/                       # 临时输出（可删除）
```

### 2.2 目录权限说明

| 目录 | 权限 | 说明 |
|------|------|------|
| `/data/ai_platform/data/` | `755` | 容器需要读写数据库文件 |
| `/data/ai_platform/licenses/` | `700` | 仅 root 可读，防止未授权访问 |
| `/data/ai_platform/datasets/` | `755` | 训练工具需要写入生成的样本 |
| `/data/ai_platform/models/` | `755` | 训练服务写入，测试服务只读 |
| `/data/ai_platform/logs/` | `777` | 容器以非 root 用户运行时需要写权限 |
| `/data/ai_platform/libs/` | `755` | 编译服务写入 |

---

## 3. 服务数据持久化映射

### 3.1 训练服务（Train）

#### 数据库
- **宿主机路径**: `/data/ai_platform/data/train/train.db`
- **容器内路径**: `/app/data/train.db`
- **环境变量**: `TRAIN_DB_PATH=/app/data/train.db`
- **存储内容**:
  - 训练任务记录（TrainingJob）
  - AI 能力配置（Capability）
  - 标注项目（AnnotationProject）
  - 标注记录（AnnotationRecord）

#### 数据集
- **宿主机路径**: `/data/ai_platform/datasets/`
- **容器内路径**: `/workspace/datasets/`
- **权限**: `rw`（训练工具如 generate_fake.py 需要写入）

#### 模型输出
- **宿主机路径**: `/data/ai_platform/models/`
- **容器内路径**: `/workspace/models/`
- **权限**: `rw`

#### 日志
- **宿主机路径**: `/data/ai_platform/logs/train/`
- **容器内路径**: `/workspace/logs/`
- **权限**: `rw`

### 3.2 授权服务（License）

#### 数据库
- **宿主机路径**: `/data/ai_platform/data/license/license.db`
- **容器内路径**: `/app/data/license.db`
- **环境变量**: `AI_LICENSE_DB=/app/data/license.db`
- **存储内容**:
  - 客户授权记录（LicenseCustomer）
  - 密钥对记录（CustomerKeyPair）
  - 授权文件元数据

#### 授权文件
- **宿主机路径**: `/data/ai_platform/licenses/`
- **容器内路径**: `/data/licenses/`
- **权限**: `rw`（仅授权服务可访问）

#### 日志
- **宿主机路径**: `/data/ai_platform/logs/license/`
- **容器内路径**: `/app/logs/`
- **权限**: `rw`

### 3.3 Redis（消息队列）

#### 持久化数据
- **宿主机路径**: `/data/ai_platform/data/redis/`
- **容器内路径**: `/data/`
- **权限**: `rw`
- **存储内容**:
  - `appendonly.aof` - AOF 持久化文件
  - `dump.rdb` - RDB 快照（如启用）
- **配置**: `--appendonly yes`（开启 AOF 持久化）

### 3.4 测试服务（Test）

#### 模型文件
- **宿主机路径**: `/data/ai_platform/models/`
- **容器内路径**: `/workspace/models/`
- **权限**: `ro`（只读）

#### 数据集
- **宿主机路径**: `/data/ai_platform/datasets/`
- **容器内路径**: `/workspace/datasets/`
- **权限**: `ro`（只读）

#### 日志
- **宿主机路径**: `/data/ai_platform/logs/test/`
- **容器内路径**: `/workspace/logs/`
- **权限**: `rw`

### 3.5 编译服务（Build）

#### 编译产物
- **宿主机路径**: `/data/ai_platform/libs/linux_x86_64/`
- **容器内路径**: `/workspace/libs/linux_x86_64/`
- **权限**: `rw`

#### 构建日志
- **宿主机路径**: `/data/ai_platform/logs/build/`
- **容器内路径**: `/app/build/backend/data/build_logs/`
- **权限**: `rw`

**注意**: 编译服务使用内存字典 `_jobs` 存储构建任务状态，无需数据库持久化。

---

## 4. Docker Compose 配置

### 4.1 卷挂载配置示例

```yaml
services:
  train:
    volumes:
      - /data/ai_platform/datasets:/workspace/datasets:rw
      - /data/ai_platform/models:/workspace/models:rw
      - /data/ai_platform/logs/train:/workspace/logs:rw
      - /data/ai_platform/data/train:/app/data:rw  # 数据库
    environment:
      - TRAIN_DB_PATH=/app/data/train.db

  license:
    volumes:
      - /data/ai_platform/licenses:/data/licenses:rw
      - /data/ai_platform/logs/license:/app/logs:rw
      - /data/ai_platform/data/license:/app/data:rw  # 数据库
    environment:
      - AI_LICENSE_DB=/app/data/license.db

  redis:
    volumes:
      - /data/ai_platform/data/redis:/data:rw  # Redis 持久化
    command: redis-server --appendonly yes
```

### 4.2 移除 Docker 匿名卷

**修改前**（不推荐）:
```yaml
volumes:
  redis-data:
    driver: local

services:
  redis:
    volumes:
      - redis-data:/data  # 使用命名卷，数据在 Docker 内部
```

**修改后**（推荐）:
```yaml
# volumes 段落已删除

services:
  redis:
    volumes:
      - /data/ai_platform/data/redis:/data:rw  # 直接映射到宿主机
```

---

## 5. 数据库架构

### 5.1 训练服务数据库 (train.db)

#### 表结构

**capabilities** - AI 能力配置
- `id` - 能力 ID
- `name` - 能力名称（如 face_detect）
- `name_cn` - 中文名称
- `framework` - 训练框架（pytorch/tensorflow）
- `script_path` - 训练脚本路径
- `dataset_path` - 数据集路径
- `hyperparams` - 超参数（JSON）
- `created_at` - 创建时间

**training_jobs** - 训练任务
- `id` - 任务 ID
- `capability_id` - 关联能力 ID
- `version` - 模型版本
- `status` - 状态（pending/running/paused/done/failed）
- `pid` - 进程 ID
- `hyperparams` - 任务超参数（JSON，覆盖能力默认值）
- `started_at` - 开始时间
- `finished_at` - 完成时间
- `error_msg` - 错误信息
- `celery_task_id` - Celery 任务 ID

**annotation_projects** - 标注项目
- `id` - 项目 ID
- `name` - 项目名称
- `annotation_type` - 标注类型（object_detection/classification 等）
- `classes` - 类别定义（JSON）
- `created_at` - 创建时间

**annotation_records** - 标注记录
- `id` - 记录 ID
- `project_id` - 关联项目 ID
- `image_path` - 图像路径
- `annotation_data` - 标注数据（JSON）
- `status` - 状态（pending/completed）
- `created_at` - 创建时间

### 5.2 授权服务数据库 (license.db)

#### 表结构

**customers** - 客户信息
- `id` - 客户 ID
- `name` - 客户名称
- `contact` - 联系方式
- `created_at` - 创建时间

**key_pairs** - 客户密钥对
- `id` - 密钥对 ID
- `customer_id` - 关联客户 ID
- `public_key` - 公钥（PEM 格式）
- `private_key` - 私钥（加密存储）
- `fingerprint` - 公钥指纹
- `created_at` - 创建时间

**licenses** - 授权记录
- `id` - 授权 ID
- `customer_id` - 关联客户 ID
- `capabilities` - 授权能力列表（JSON）
- `valid_until` - 有效期
- `license_file_path` - license.bin 文件路径
- `created_at` - 创建时间

---

## 6. 数据备份与恢复

### 6.1 备份策略

#### 完整备份（推荐）
```bash
# 备份整个数据目录（包含所有数据库、Redis 数据、授权文件等）
tar -czf ai_platform_backup_$(date +%Y%m%d).tar.gz /data/ai_platform/data/
```

#### 分模块备份
```bash
# 仅备份训练相关数据
tar -czf train_backup_$(date +%Y%m%d).tar.gz \
    /data/ai_platform/data/train/ \
    /data/ai_platform/models/ \
    /data/ai_platform/datasets/

# 仅备份授权相关数据
tar -czf license_backup_$(date +%Y%m%d).tar.gz \
    /data/ai_platform/data/license/ \
    /data/ai_platform/licenses/
```

### 6.2 数据恢复

#### 完整恢复
```bash
# 停止所有服务
cd /path/to/ai_platform/deploy
docker compose down

# 恢复数据
tar -xzf ai_platform_backup_20260331.tar.gz -C /

# 重启服务
docker compose up -d
```

#### 单个数据库恢复
```bash
# 停止相关服务
docker compose stop train

# 恢复数据库文件
cp backup/train.db /data/ai_platform/data/train/train.db

# 重启服务
docker compose start train
```

### 6.3 定期备份建议

| 数据类型 | 备份频率 | 保留时长 |
|----------|----------|----------|
| 数据库（train.db, license.db） | 每天 | 30 天 |
| Redis 数据 | 每天 | 7 天 |
| 训练模型 | 每周 | 永久保留重要版本 |
| 数据集 | 初次备份后按需 | 永久 |
| 授权文件 | 每周 | 永久 |

---

## 7. 数据迁移

### 7.1 迁移到新服务器

```bash
# 在旧服务器上
# 1. 停止服务
docker compose down

# 2. 打包数据
tar -czf ai_platform_full.tar.gz /data/ai_platform/

# 3. 传输到新服务器
scp ai_platform_full.tar.gz newserver:/tmp/

# 在新服务器上
# 4. 解压数据
tar -xzf /tmp/ai_platform_full.tar.gz -C /

# 5. 克隆代码仓库
git clone https://github.com/LeeYou/ai_platform.git

# 6. 启动服务
cd ai_platform/deploy
docker compose up -d
```

### 7.2 迁移单个服务数据

```bash
# 例如：仅迁移训练服务数据
tar -czf train_data.tar.gz /data/ai_platform/data/train/

# 在新服务器上
tar -xzf train_data.tar.gz -C /
```

---

## 8. 故障排查

### 8.1 数据库文件权限问题

**症状**: 容器启动失败，日志显示 "Permission denied: /app/data/train.db"

**解决方案**:
```bash
# 检查目录权限
ls -la /data/ai_platform/data/train/

# 修复权限
chmod -R 755 /data/ai_platform/data/
chown -R 1000:1000 /data/ai_platform/data/train/  # 1000 是容器内用户 UID
```

### 8.2 Redis AOF 文件损坏

**症状**: Redis 容器无法启动，日志显示 "Bad file format reading the append only file"

**解决方案**:
```bash
# 使用 redis-check-aof 修复
docker run --rm -v /data/ai_platform/data/redis:/data \
    redis:7-alpine redis-check-aof --fix /data/appendonly.aof

# 重启 Redis
docker compose restart redis
```

### 8.3 数据库迁移

**症状**: 升级版本后数据库架构不兼容

**解决方案**:
```bash
# 备份旧数据库
cp /data/ai_platform/data/train/train.db /data/ai_platform/data/train/train.db.backup

# 运行迁移脚本（如有）
docker compose exec train python migrate_xxx.py
```

---

## 9. 最佳实践

### 9.1 数据安全
1. **定期备份**：设置自动化备份任务（cron）
2. **异地存储**：备份文件存储到远程服务器或对象存储
3. **权限控制**：严格控制 `/data/ai_platform/` 目录权限
4. **加密存储**：敏感数据（如私钥）使用加密存储

### 9.2 性能优化
1. **SSD 存储**：数据库和 Redis 数据建议使用 SSD
2. **定期清理**：清理过期的训练日志和临时文件
3. **监控磁盘**：设置磁盘空间监控告警

### 9.3 容器化原则
1. **无状态容器**：容器内不保存任何持久化数据
2. **环境变量配置**：所有路径通过环境变量配置
3. **卷挂载声明**：明确声明所有数据卷挂载

---

## 10. 变更记录

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|----------|
| v1.0 | 2026-03-31 | Claude | 初始版本：设计数据持久化架构 |

---

**文档维护**: 技术架构组
**联系方式**: tech@agilestar.cn
