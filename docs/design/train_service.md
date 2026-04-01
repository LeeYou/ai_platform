# 训练子系统设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.1 | 2026-03-30**

---

## 1. 概述

训练子系统负责 AI 能力模型的配置、训练执行、进度监控和模型包导出，所有操作通过 Web 可视化界面完成，无需登录服务器手动操作。

---

## 2. 容器设计

| 属性 | 值 |
|------|-----|
| 镜像名 | `agilestar/ai-train:latest` |
| 基础镜像 | `nvidia/cuda:12.1-cudnn8-devel-ubuntu22.04` |
| 服务端口 | 8001（Web 管理界面） |
| 后端框架 | Python FastAPI + Celery（异步任务） |
| 前端框架 | Vue3 + Element Plus |
| 训练框架 | PyTorch ≥2.0（默认），支持 PaddlePaddle 扩展 |

### 挂载目录

| 宿主机路径 | 容器路径 | 模式 |
|-----------|---------|------|
| `/data/ai_platform/datasets/` | `/workspace/datasets` | 读写 |
| `/data/ai_platform/models/` | `/workspace/models` | 读写 |
| `/data/ai_platform/logs/train/` | `/workspace/logs` | 读写 |

---

## 3. Web 管理页面功能

### 3.1 页面结构

```
训练管理 Web
├── 数据集管理
│   ├── 数据集列表（按能力分类展示）
│   ├── 文件浏览（目录树 + 文件数量统计）
│   └── 样本预览
├── ★ 样本标注
│   ├── 标注项目列表（新建/编辑/删除/归档）
│   ├── 标注工作台
│   │   ├── 二分类标注（正/负样本 + 快捷键）
│   │   ├── 多分类标注（标签面板 + 快捷键）
│   │   ├── 目标检测标注（矩形框绘制 + 标签选择）
│   │   ├── OCR标注（多边形区域 + 文字输入）
│   │   └── 图像分割标注（多边形 + 标签）
│   └── 导出标注结果（分类/YOLO/OCR格式）
├── 能力配置
│   ├── AI 能力列表（增删改）
│   ├── 训练脚本关联
│   └── 超参数模板管理
├── 训练控制
│   ├── 新建训练任务
│   ├── 任务列表（运行中/已完成/失败）
│   ├── 实时日志流（WebSocket）
│   ├── 训练曲线（loss / accuracy 折线图）
│   └── 启动 / 暂停 / 停止 操作
└── 模型管理
    ├── 已导出模型版本列表
    ├── 标记最优版本
    └── 导出为标准模型包
```

### 3.2 功能模块详述

#### 数据集管理

- 展示 `/workspace/datasets/` 下所有能力目录
- 显示每个能力数据集的文件数量、总大小、最后更新时间
- 支持样本图片缩略图预览

#### 样本标注

- 标注项目管理：创建标注项目，关联 AI 能力、标注类型、神经网络选型
- 支持五种标注类型：二分类、多分类、目标检测、OCR 文字识别、图像分割
- 标注工作台：大图展示 + 工具栏 + 样本导航 + 进度追踪
- 键盘快捷键支持：数字键标注分类，方向键翻页
- 一键导出：生成训练框架兼容的数据格式（分类目录结构 / YOLO txt / OCR txt）
- 详细设计见 `docs/design/annotation_service.md`

#### 能力配置

- 为每个 AI 能力维护一份配置记录：
  - 能力名称（英文标识，如 `face_detect`）
  - 能力描述（中文，如"人脸检测"）
  - 数据集路径（自动关联 `/workspace/datasets/<capability>/`）
  - 训练脚本路径（如 `scripts/face_detect/train.py`）
  - 超参数配置（支持 JSON 编辑或表单编辑）
- 支持从模板新建能力配置（复用超参数默认值）

#### 训练控制

- 选择能力 + 配置版本 → 一键启动训练
- 训练任务在后台 Celery Worker 中执行，主进程不阻塞
- 实时通过 WebSocket 推送训练日志到前端
- 每隔 10 秒推送最新 epoch 损失和精度指标，前端绘制曲线
- 支持暂停（发送 SIGSTOP 到训练进程）和停止（SIGTERM）

#### 模型管理

- 训练完成后，系统自动触发导出：将原始 checkpoint 转换为 ONNX 格式
- 按版本号归档到 `/workspace/models/<capability>/<version>/`
- 用户可手动标记某版本为"当前版本"（更新 `current` 符号链接）

---

## 4. 训练执行流程

```
用户在 Web 页面配置训练参数
        ↓
后端 API 验证数据集路径是否存在
        ↓
创建 Celery 训练任务，生成 task_id
        ↓
Celery Worker 启动训练子进程
  (subprocess: python train.py --config <config.json>)
        ↓
训练进程输出日志 → Redis Pub/Sub → WebSocket → 前端实时展示
        ↓
训练完成（exit code 0）
        ↓
自动导出 ONNX 模型
        ↓
生成 manifest.json 和 checksum
        ↓
写入 /workspace/models/<capability>/<version>/
        ↓
更新 current 符号链接（可选，需用户确认）
```

---

## 5. 标准模型包格式

每个训练完成的模型版本输出为一个**标准模型包目录**：

```
/workspace/models/face_detect/v1.0.0/
├── model.onnx              # 推理模型文件
├── manifest.json           # 元数据与校验信息
├── preprocess.json         # 预处理配置
├── labels.json             # 标签定义
└── checksum.sha256         # 文件完整性校验
```

### manifest.json 示例

```json
{
  "capability": "face_detect",
  "capability_name_cn": "人脸检测",
  "model_version": "1.0.0",
  "backend": "onnxruntime",
  "input_size": [1, 3, 640, 640],
  "input_format": "NCHW",
  "preprocessing": {
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
    "normalize": true,
    "color_format": "RGB"
  },
  "threshold": 0.5,
  "labels": ["face"],
  "build_env": {
    "framework": "pytorch",
    "framework_version": "2.1.0",
    "cuda_version": "12.1",
    "trained_at": "2026-03-27T07:00:00Z",
    "trained_by": "agilestar/ai-train:1.0.0"
  },
  "checksum": {
    "model_file": "sha256:abc123...",
    "algorithm": "sha256"
  },
  "company": "agilestar.cn"
}
```

### preprocess.json 示例

```json
{
  "resize": { "width": 640, "height": 640, "keep_ratio": true },
  "pad_value": [114, 114, 114],
  "normalize": true,
  "mean": [0.485, 0.456, 0.406],
  "std": [0.229, 0.224, 0.225],
  "color_convert": "BGR2RGB"
}
```

---

## 6. 训练脚本规范

每个 AI 能力的训练脚本放在 `train/scripts/<capability>/` 目录下，必须遵循以下接口约定：

```
train/scripts/face_detect/
├── train.py          # 主训练脚本，接收 --config 参数
├── export.py         # 模型导出脚本（checkpoint → ONNX）
├── config.json       # 默认超参数配置
└── requirements.txt  # 额外 Python 依赖
```

`train.py` 命令行参数：

```bash
python train.py \
  --config config.json \        # 超参数配置
  --dataset /workspace/datasets/face_detect/ \  # 数据集路径
  --output /workspace/models/face_detect/v1.0.0/ \  # 输出路径
  --version 1.0.0               # 版本号
```

标准输出格式（供日志解析）：

```
[EPOCH 1/100] loss=0.8234 accuracy=0.6543
[EPOCH 2/100] loss=0.7123 accuracy=0.7012
...
[DONE] model saved to /workspace/models/face_detect/v1.0.0/
```

---

## 7. 支持的 AI 能力（首期）

| 能力标识 | 中文名称 | 算法类型 |
|---------|---------|---------|
| `face_detect` | 人脸检测 | 目标检测（YOLO系列） |
| `handwriting_reco` | 手写签字识别 | 图像分类 / OCR |
| `recapture_detect` | 翻拍检测 | 二分类 |
| `id_card_classify` | 证件分类识别 | 多分类 |

---

## 8. 扩展新 AI 能力

1. 在 `/data/ai_platform/datasets/<new_capability>/` 下准备原始数据集
2. 在 Web 样本标注页面创建标注项目，选择标注类型和网络选型，完成样本标注
3. 导出标注数据为训练兼容格式
4. 在 `train/scripts/<new_capability>/` 下按上述规范创建训练脚本
5. 在 Web 能力配置页面新增能力条目
6. 配置数据集路径和超参数，启动训练

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
