# 样本标注子系统设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-30**

---

## 1. 概述

样本标注子系统作为训练容器的核心功能模块之一，提供 Web 可视化标注工具，支持多种 AI 训练常见的标注类型。标注子系统与训练子系统深度集成，形成"标注 → 训练 → 测试 → 授权 → 编译 → 生产 → 迭代"的完整闭环。

Integration into train container (port 8001), not a separate service.

## 2. 支持的标注类型

| 标注类型 | 英文标识 | 适用场景 | 标注格式 |
|---------|---------|---------|---------|
| 二分类 | binary_classification | 活体检测、翻拍检测、屏幕攻击检测 | {"label": 0/1, "label_name": "真/假"} |
| 多分类 | multi_classification | 证件分类、场景分类、表情识别 | {"label": 2, "label_name": "护照"} |
| 目标检测 | object_detection | 人脸检测、车牌检测、物体检测(YOLO等) | {"boxes": [{"x","y","w","h","label"}]} |
| OCR文字识别 | ocr | 文字识别、车牌号识别、合同关键字段 | {"regions": [{"points":[[x,y]...],"text":"..."}]} |
| 图像分割 | segmentation | 语义分割、实例分割 | {"masks": [{"points":[[x,y]...],"label":"..."}]} |

## 3. 数据模型

### 3.1 标注项目 (AnnotationProject)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | str(128) | 项目名称（如"活体检测v2标注"） |
| capability_id | int FK | 关联的AI能力 |
| annotation_type | str(32) | 标注类型（binary_classification/multi_classification/object_detection/ocr/segmentation）|
| network_type | str(64) | 神经网络选型（resnet18/yolov8/crnn/unet等） |
| dataset_path | str(512) | 数据集路径 |
| label_config | JSON | 标签定义配置 |
| status | str(16) | 状态（in_progress/completed/archived）|
| total_samples | int | 总样本数 |
| annotated_samples | int | 已标注样本数 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 3.2 标注记录 (AnnotationRecord)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| project_id | int FK | 关联的标注项目 |
| file_path | str(512) | 样本文件相对路径 |
| annotation_data | JSON | 标注数据（格式随标注类型不同） |
| annotated_by | str(64) | 标注人员标识 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 3.3 label_config 示例

二分类：
```json
{"labels": [{"id": 0, "name": "负样本"}, {"id": 1, "name": "正样本"}]}
```

多分类：
```json
{"labels": [{"id": 0, "name": "身份证"}, {"id": 1, "name": "护照"}, {"id": 2, "name": "驾驶证"}]}
```

目标检测：
```json
{"labels": [{"id": 0, "name": "人脸", "color": "#FF0000"}, {"id": 1, "name": "人体", "color": "#00FF00"}]}
```

OCR：
```json
{"labels": [{"id": 0, "name": "text_region"}], "recognize_text": true}
```

## 4. Web 页面设计

### 4.1 页面结构

```
训练管理 Web (扩展)
├── 仪表盘（已有）
├── ★ 样本标注 ← 新增
│   ├── 标注项目列表
│   │   ├── 新建项目（选择能力 + 标注类型 + 网络选型 + 标签配置）
│   │   ├── 项目进度总览
│   │   └── 项目管理（编辑/归档/删除）
│   └── 标注工作台
│       ├── 图片/文件查看器
│       ├── 标注工具栏（根据标注类型动态切换）
│       │   ├── 二分类：正/负样本按钮 + 快捷键
│       │   ├── 多分类：标签选择面板 + 快捷键
│       │   ├── 目标检测：矩形框绘制 + 标签选择
│       │   └── OCR：多边形区域绘制 + 文字输入
│       ├── 样本导航（上一张/下一张/跳转）
│       ├── 标注进度条
│       └── 导出标注结果（生成训练数据格式）
├── 数据集管理（已有）
├── 能力配置（已有）
├── 训练控制（已有）
└── 模型管理（已有）
```

### 4.2 标注工作台工具详述

#### 二分类标注工具
- 大图展示当前样本
- 两个按钮：正样本(1) / 负样本(0)
- 键盘快捷键：1=正样本，0=负样本，→=下一张，←=上一张
- 自动跳转下一张未标注样本

#### 多分类标注工具
- 大图展示当前样本
- 标签面板（根据 label_config 动态生成）
- 键盘快捷键：数字键对应标签ID
- 支持搜索过滤标签

#### 目标检测标注工具
- Canvas 图片展示
- 鼠标拖拽绘制矩形标注框
- 框选后弹出标签选择
- 支持框的拖拽移动、缩放、删除
- 显示已标注框列表

#### OCR标注工具
- Canvas 图片展示
- 多边形区域绘制（4点或多点）
- 区域选中后弹出文字输入框
- 显示已标注区域列表及对应文字

## 5. API 设计

### 5.1 标注项目 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/annotations/projects | 列出所有标注项目 |
| POST | /api/v1/annotations/projects | 创建标注项目 |
| GET | /api/v1/annotations/projects/{id} | 获取项目详情 |
| PUT | /api/v1/annotations/projects/{id} | 更新项目 |
| DELETE | /api/v1/annotations/projects/{id} | 删除项目 |
| GET | /api/v1/annotations/projects/{id}/stats | 获取项目统计 |
| POST | /api/v1/annotations/projects/{id}/export | 导出标注为训练数据格式 |

### 5.2 标注记录 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/annotations/projects/{id}/samples | 获取样本列表（分页，含标注状态）|
| GET | /api/v1/annotations/projects/{id}/samples/{record_id} | 获取单条标注 |
| POST | /api/v1/annotations/projects/{id}/annotate | 保存/更新标注 |
| DELETE | /api/v1/annotations/projects/{id}/samples/{record_id} | 删除标注 |

### 5.3 图片服务 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/annotations/image?path=... | 返回图片文件（安全路径校验）|

## 6. 导出格式

标注完成后，支持一键导出为各训练框架兼容的格式：

### 6.1 二分类/多分类导出
```
export_dir/
├── train/
│   ├── class_0/  (或 negative/)
│   │   ├── img001.jpg
│   │   └── ...
│   └── class_1/  (或 positive/)
│       ├── img002.jpg
│       └── ...
├── val/
│   └── (同结构)
└── labels.json
```

### 6.2 目标检测导出（YOLO格式）
```
export_dir/
├── images/
│   ├── train/
│   └── val/
├── labels/
│   ├── train/
│   │   ├── img001.txt  (class_id cx cy w h 归一化)
│   │   └── ...
│   └── val/
└── data.yaml
```

### 6.3 OCR导出
```
export_dir/
├── images/
│   ├── img001.jpg
│   └── ...
├── labels/
│   ├── img001.txt  (每行: x1,y1,x2,y2,...,text)
│   └── ...
└── meta.json
```

## 7. 与训练子系统联动

### 7.1 标注到训练的关联

- 标注项目绑定 AI 能力（capability_id）
- 标注项目记录神经网络选型（network_type）
- 导出标注数据到数据集目录后，训练任务自动关联
- 训练任务页面显示关联的标注项目和标注统计

### 7.2 迭代训练流程

```
1. 创建标注项目 → 选择能力、标注类型、网络选型
2. 标注样本 → Web工具标注
3. 导出标注 → 生成训练数据格式到数据集目录
4. 启动训练 → 自动关联标注项目
5. 测试模型 → 在测试子系统验证
6. 如效果不佳 → 补充标注样本 → 重新训练（迭代）
7. 效果达标 → 编译SO → 生产部署
```

## 8. 网络选型参考

| 标注类型 | 推荐网络 | 说明 |
|---------|---------|------|
| 二分类 | ResNet18, MobileNetV3, EfficientNet-B0 | 轻量级分类网络 |
| 多分类 | ResNet50, EfficientNet-B3, ViT-Small | 中型分类网络 |
| 目标检测 | YOLOv8n, YOLOv8s, SSD-MobileNet, FCOS | 实时检测网络 |
| OCR | CRNN, PaddleOCR-PP-OCRv4, TrOCR | 文字识别网络 |
| 图像分割 | U-Net, DeepLabV3+, Mask R-CNN | 分割网络 |

## 9. 安全设计

- 图片服务API做路径安全校验，禁止路径遍历攻击
- 标注数据JSON格式校验，防止注入
- 文件路径必须在数据集目录范围内
- 导出操作仅写入指定数据集目录

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
