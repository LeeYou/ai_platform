# AI平台数据同步架构设计

## 架构原则

### 内部开发环境：API驱动通信

训练、测试、授权、编译等内部服务通过REST API互相通信，实现专业的数据同步：

```
┌─────────────────────────────────────────────────────────────┐
│                     内部开发环境                              │
│                                                               │
│  ┌──────────┐         ┌──────────┐         ┌──────────┐   │
│  │ 训练服务 │────────>│ 数据库   │<────────│ 测试服务 │   │
│  │ :8001    │  写入   │ SQLite   │  读取   │ :8002    │   │
│  └──────────┘         └──────────┘         └──────────┘   │
│       │                                           │          │
│       │ API                                       │ API      │
│       v                                           v          │
│  ┌──────────┐                              ┌──────────┐   │
│  │ 授权服务 │                              │ 编译服务 │   │
│  │ :8003    │                              │ :8004    │   │
│  └──────────┘                              └──────────┘   │
│       │                                           │          │
│       └───────────────API通信───────────────────┘          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 生产环境：目录扫描机制

生产服务独立部署，通过扫描目录发现AI能力：

```
┌─────────────────────────────────────────────────────────────┐
│                     生产环境                                  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 生产服务 :8080                                         │  │
│  │                                                        │  │
│  │  ┌───────────────┐                                    │  │
│  │  │ C++ Runtime   │                                    │  │
│  │  │               │                                    │  │
│  │  │ 扫描并加载：    │                                    │  │
│  │  │ 1. 镜像内置目录 │                                    │  │
│  │  │ 2. 宿主机挂载   │                                    │  │
│  │  └───────────────┘                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                       │                                      │
│                       v                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 宿主机挂载目录                                        │   │
│  │  - /data/ai_platform/models/                         │   │
│  │  - /data/ai_platform/libs/                           │   │
│  │  - /data/ai_platform/licenses/                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 详细设计

### 1. 训练服务（数据源）

**职责**：AI能力元数据的唯一数据源

**API端点**：
```
GET /api/v1/capabilities
返回：[
  {
    "id": 1,
    "name": "face_detect",
    "name_cn": "人脸检测",
    "description": "基于YOLOv8的人脸检测",
    "dataset_path": "/workspace/datasets/face_detect",
    "script_path": "/app/scripts/face_detect",
    "hyperparams": {...},
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z"
  },
  ...
]
```

**数据存储**：
- 数据库：SQLite（开发环境）/ PostgreSQL（生产环境）
- 表：capabilities, training_jobs, model_versions
- 文件系统：`/workspace/models/<capability>/current/`

**目录结构**：
```
/workspace/models/
├── face_detect/
│   └── current/
│       ├── manifest.json      # 元数据
│       ├── model.onnx         # ONNX模型
│       └── ...
└── desktop_recapture_detect/
    └── current/
        ├── manifest.json
        ├── model.onnx
        └── ...
```

### 2. 测试服务

**职责**：模型测试和验证

**数据获取**：
- 能力列表：读取挂载的 `/workspace/models/` 目录（只读）
- 能力元数据：可选择调用训练服务API获取详细信息

**挂载**：
```yaml
volumes:
  - /data/ai_platform/models:/workspace/models:ro
  - /data/ai_platform/datasets:/workspace/datasets:ro
```

### 3. 授权服务

**职责**：License管理和签名

**数据获取**：
- 能力列表：调用训练服务API `GET /api/v1/capabilities`
- 返回能力名称列表供用户选择授权

**API端点**：
```
GET /api/v1/keys           # 密钥对列表
POST /api/v1/licenses      # 创建授权
GET /api/v1/licenses       # 授权列表
```

### 4. 编译服务

**职责**：编译AI能力SO库

**数据获取方式**：
```python
# 1. 从训练服务API获取已训练的能力
async with httpx.AsyncClient() as client:
    resp = await client.get(f"{TRAIN_SERVICE_URL}/api/v1/capabilities")
    train_caps = resp.json()

# 2. 扫描本地源代码目录
source_caps = os.listdir("/app/cpp/capabilities")

# 3. 返回交集：既有训练模型又有源代码的能力
buildable = [cap for cap in train_caps if cap['name'] in source_caps]
```

**环境变量**：
```yaml
environment:
  - TRAIN_SERVICE_URL=http://train:8001
  - LICENSE_SERVICE_URL=http://license:8003
```

**依赖关系**：
```yaml
depends_on:
  - train
  - license
```

### 5. 生产服务（独立部署）

**职责**：AI推理服务

**能力发现机制**：
```python
# C++ Runtime启动时扫描目录
def _init_runtime():
    libs_dir = resolve_libs_dir()        # /mnt/ai_platform/libs
    models_dir = resolve_models_dir()    # /mnt/ai_platform/models

    # 扫描libs目录下的.so文件
    # 扫描models目录下包含manifest.json的能力
    # 动态加载到Runtime

# API查询已加载的能力
def list_capabilities():
    runtime = get_runtime()
    return runtime.get_capabilities()  # 从Runtime获取
```

**目录优先级**：
1. 宿主机挂载目录（/mnt/ai_platform/）优先
2. 镜像内置目录（/app/）作为备份

**支持热加载**：
```bash
# 运维人员操作
1. 将新的模型和SO库放到宿主机目录
   /data/ai_platform/models/new_capability/current/
   /data/ai_platform/libs/linux_x86_64/new_capability/

2. 调用管理API触发重载
   curl -X POST http://localhost:8080/api/v1/admin/reload \
     -H "Authorization: Bearer ${ADMIN_TOKEN}"

3. 新能力自动加载并可用
   curl http://localhost:8080/api/v1/capabilities
```

## 统一目录结构规范

### 宿主机目录结构

```
/data/ai_platform/
├── models/                          # 模型目录（所有服务）
│   ├── face_detect/
│   │   └── current/
│   │       ├── manifest.json        # 必需：模型元数据
│   │       ├── model.onnx          # 必需：ONNX模型文件
│   │       └── ...
│   └── desktop_recapture_detect/
│       └── current/
│           ├── manifest.json
│           ├── model.onnx
│           └── ...
│
├── libs/                            # 编译输出（编译服务写入）
│   ├── linux_x86_64/
│   │   ├── face_detect/
│   │   │   └── lib/
│   │   │       ├── libface_detect.so
│   │   │       └── libai_runtime.so
│   │   └── desktop_recapture_detect/
│   │       └── lib/
│   │           ├── libdesktop_recapture_detect.so
│   │           └── libai_runtime.so
│   ├── linux_aarch64/               # ARM64编译输出
│   └── windows_x86_64/              # Windows编译输出
│
├── licenses/                        # 授权文件（授权服务写入）
│   ├── license.bin                  # 生产环境授权文件
│   └── pubkey.pem                   # 对应的公钥
│
├── datasets/                        # 数据集（训练服务）
│   ├── face_detect/
│   └── desktop_recapture_detect/
│
├── logs/                            # 日志目录
│   ├── train/
│   ├── test/
│   ├── license/
│   ├── build/
│   └── prod/
│
└── data/                            # 数据库等持久化数据
    ├── train/train.db
    ├── license/license.db
    └── redis/
```

### manifest.json格式规范

```json
{
  "capability": "face_detect",
  "model_version": "1.0.0",
  "framework": "onnxruntime",
  "model_file": "model.onnx",
  "input_shape": [1, 3, 640, 640],
  "output_names": ["output0"],
  "classes": ["face", "occluded_face"],
  "confidence_threshold": 0.5,
  "iou_threshold": 0.45,
  "export_date": "2026-01-15T10:30:00Z",
  "training_job_id": 123,
  "training_config": {
    "epochs": 100,
    "batch_size": 16,
    "learning_rate": 0.001
  }
}
```

## 数据流转流程

### 完整AI能力开发流程

```
┌────────────────────────────────────────────────────────────────┐
│ 1. 训练阶段                                                      │
├────────────────────────────────────────────────────────────────┤
│ 用户 → 训练服务Web → 创建训练任务 → 后台训练                     │
│                                                                  │
│ 训练完成 → 导出ONNX → 生成manifest.json                         │
│          → 写入 /data/ai_platform/models/<cap>/current/         │
│          → 数据库记录状态                                        │
└────────────────────────────────────────────────────────────────┘
                              │
                              v
┌────────────────────────────────────────────────────────────────┐
│ 2. 测试阶段                                                      │
├────────────────────────────────────────────────────────────────┤
│ 用户 → 测试服务Web → 选择能力（从models目录扫描）                │
│                    → 上传测试图片 → Python推理测试               │
│                    → 返回测试结果                                │
└────────────────────────────────────────────────────────────────┘
                              │
                              v
┌────────────────────────────────────────────────────────────────┐
│ 3. 编译阶段                                                      │
├────────────────────────────────────────────────────────────────┤
│ 用户 → 编译服务Web → 获取能力列表（调用训练服务API）              │
│                    → 选择能力 + 密钥对                           │
│                    → CMake编译 → 生成SO库                        │
│                    → 写入 /data/ai_platform/libs/<arch>/<cap>/  │
└────────────────────────────────────────────────────────────────┘
                              │
                              v
┌────────────────────────────────────────────────────────────────┐
│ 4. 授权阶段                                                      │
├────────────────────────────────────────────────────────────────┤
│ 用户 → 授权服务Web → 获取能力列表（调用训练服务API）              │
│                    → 创建授权（选择能力+时间+客户）               │
│                    → 签名授权文件                                │
│                    → 写入 /data/ai_platform/licenses/           │
└────────────────────────────────────────────────────────────────┘
                              │
                              v
┌────────────────────────────────────────────────────────────────┐
│ 5. 生产部署                                                      │
├────────────────────────────────────────────────────────────────┤
│ 运维 → 打包交付物：                                              │
│       1. 生产服务镜像（agilestar/ai-prod:latest）                │
│       2. 宿主机目录结构（models/ + libs/ + licenses/）           │
│                                                                  │
│ 客户 → 启动生产容器                                              │
│       → C++ Runtime扫描目录                                      │
│       → 动态加载SO和模型                                         │
│       → 提供推理API                                              │
└────────────────────────────────────────────────────────────────┘
```

## API通信矩阵

| 服务          | 调用的API                                | 目的                     |
|---------------|------------------------------------------|--------------------------|
| 训练服务      | -                                        | 数据源，不调用其他服务    |
| 测试服务      | （可选）训练服务 `/api/v1/capabilities`  | 获取能力元数据           |
| 授权服务      | 训练服务 `/api/v1/capabilities`          | 获取能力列表供授权       |
| 编译服务      | 训练服务 `/api/v1/capabilities`          | 获取可编译的能力列表     |
| 编译服务      | 授权服务 `/api/v1/keys`                  | 获取密钥对列表           |
| 生产服务      | 无（独立部署）                           | 扫描目录                 |

## 优势分析

### 内部服务使用API的优势

1. **数据一致性**：训练服务作为唯一数据源，避免数据不同步
2. **解耦合**：各服务独立开发和部署，通过API契约通信
3. **可扩展性**：新增服务只需调用现有API，无需访问文件系统
4. **权限控制**：API层可以实现细粒度的权限控制
5. **审计追踪**：所有数据访问通过API，便于日志记录和审计
6. **专业架构**：符合微服务架构的最佳实践

### 生产服务使用目录扫描的优势

1. **独立部署**：无需依赖其他服务，适合客户环境部署
2. **高可用性**：不依赖网络连接，服务更稳定
3. **性能优化**：本地文件读取，无网络延迟
4. **热加载支持**：新增文件到目录即可自动发现
5. **简化运维**：客户只需管理文件，无需维护API连接
6. **安全隔离**：生产环境与开发环境完全隔离

## 故障处理

### 训练服务不可用

**影响**：编译服务和授权服务无法获取能力列表

**解决方案**：
```python
# 编译服务降级处理
try:
    caps = await fetch_from_train_service()
except Exception:
    logger.error("Train service unavailable")
    return []  # 返回空列表，前端显示错误提示
```

### 目录结构不规范

**检测**：生产服务启动时验证目录结构
```python
required_dirs = ["models", "libs", "licenses"]
for d in required_dirs:
    if not os.path.isdir(f"/mnt/ai_platform/{d}"):
        logger.error(f"Required directory missing: {d}")
```

**修复**：运行初始化脚本
```bash
bash deploy/mount_template/init_host_dirs.sh
```

## 总结

本架构设计实现了：

✅ **内部服务API通信**：专业、解耦、可扩展
✅ **生产服务目录扫描**：独立、稳定、易部署
✅ **统一目录结构**：规范、兼容、易维护
✅ **热加载支持**：灵活、高效、零停机
✅ **清晰的职责划分**：每个服务职责明确

这是适合AI平台特点的最佳架构方案。
