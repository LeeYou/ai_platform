# AI 能力平台 —— 桌面翻拍检测能力操作指南

**北京爱知之星科技股份有限公司 (Agile Star)**
**版本:** v1.0 | **日期:** 2026-03-30 | **文档编号:** CAP-DRCAP-001
**官网：[agilestar.cn](https://agilestar.cn)**

---

## 目录

1. [概述](#1-概述)
2. [性能指标要求](#2-性能指标要求)
3. [数据集准备](#3-数据集准备)
4. [模型架构与框架](#4-模型架构与框架)
5. [数据集放置位置](#5-数据集放置位置)
6. [完整操作流程](#6-完整操作流程)
7. [API 调用示例](#7-api-调用示例)
8. [训练超参数说明](#8-训练超参数说明)
9. [假样本生成详解](#9-假样本生成详解)
10. [常见问题](#10-常见问题)
11. [性能基准](#11-性能基准)

---

## 1. 概述

### 1.1 能力简介

**桌面翻拍检测 (desktop_recapture_detect)** 是 AI 能力平台提供的视觉类安全检测能力，属于二分类范畴。
该能力可判断摄像头画面是 **真实人像（real）** 还是 **桌面照片浏览器翻拍（fake）**，用于检测虚拟摄像头作弊行为。

典型应用场景：视频面签、在线考试、远程身份核验等需要确认用户真实在线的业务环节。

### 1.2 核心特性

| 特性           | 描述                                                           |
|---------------|---------------------------------------------------------------|
| 二分类检测     | 输出 real（真实肖像）或 fake（桌面翻拍），以及 P(fake) 置信度      |
| 模板驱动生成   | 自动合成假样本：桌面截图、照片浏览器模板 × 真实肖像组合              |
| 两阶段训练     | Phase 1 冻结 backbone 训练分类头 → Phase 2 全参数微调 + 早停       |
| 轻量模型       | EfficientNet-B0，ONNX 体积 < 20 MB，推理速度快                   |
| 跨平台部署     | 支持 Linux x86_64 / aarch64，Windows x64，含 Docker 与 SO 交付   |

### 1.3 来源

迁移自 [LeeYou/recapture_detect](https://github.com/LeeYou/recapture_detect)（dev 分支），适配 ai_platform 训练 → 测试 → 编译 → 部署全链路。

### 1.4 全链路流程总览

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 素材准备   │───▶│ 假样本生成 │───▶│ 模型训练   │───▶│ 模型评估   │
│ (肖像+模板)│    │ (:8001)  │    │ (:8001)  │    │ (:8001)  │
└──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                     │
┌──────────┐    ┌──────────┐    ┌──────────┐         │
│ 生产部署   │◀───│ 推理库编译 │◀───│ 模型测试   │◀────────┘
│ (:8080)  │    │ (:8004)  │    │ (:8002)  │
└──────────┘    └─────┬────┘    └──────────┘
                ┌─────▼────┐
                │ 授权管理   │
                │ (:8003)  │
                └──────────┘
```

---

## 2. 性能指标要求

| 指标              | 要求                 | 说明                                   |
|------------------|---------------------|---------------------------------------|
| 模型体积          | **< 20 MB**         | ONNX 格式，EfficientNet-B0             |
| 分类精度 (AUC-ROC)| **> 0.98**          | 在平衡验证集上评测                       |
| Accuracy         | **> 96%**           | 二分类准确率                             |
| F1 Score         | **> 0.96**          | 综合 precision + recall                 |
| CPU 推理延迟      | **< 30 ms**         | Intel i7-12700，单张 224×224 图像        |
| GPU 推理延迟      | **< 5 ms**          | NVIDIA RTX 3060，单张 224×224 图像       |
| 输入分辨率        | **224 × 224 px**    | ImageNet 归一化                          |

---

## 3. 数据集准备

### 3.1 数据来源

桌面翻拍检测不依赖现成公开数据集，而是 **基于模板自动合成** 假样本。需要准备以下素材：

| 素材类型               | 说明                                          | 数量建议    |
|-----------------------|----------------------------------------------|-----------|
| 真实肖像 (real)        | 摄像头直拍的真人面部照片                         | ≥ 200 张   |
| 桌面截图模板            | 不同桌面壁纸/分辨率的截图                        | ≥ 10 张    |
| 空白查看器模板          | 照片浏览器窗口截图（空白区域 RGB ≈ 245,245,245） | ≥ 5 张     |
| 带图查看器模板          | 照片浏览器窗口截图（已打开一张图片）              | ≥ 5 张     |
| 手动翻拍截图（可选）     | 用摄像头实际翻拍桌面的截图                       | 0-50 张    |

### 3.2 素材采集要点

**真实肖像：**
- 包含不同光照、角度、距离、背景的真人面部
- 建议多人参与采集，增加多样性
- 支持格式：JPG / JPEG / PNG / BMP / WebP

**桌面截图模板：**
- 截取完整桌面（含任务栏、壁纸等）
- 覆盖不同操作系统外观（Windows / macOS / Linux）
- 不同分辨率：1920×1080、2560×1440、1366×768 等

**查看器模板：**
- 截取照片浏览器窗口（如 Windows 照片、macOS 预览等）
- `pic_viewer/`：空白查看器（刚打开、无图片状态）
- `pic_viewer_temp2/`：查看器中已打开一张非人像图片

---

## 4. 模型架构与框架

### 4.1 模型选型：EfficientNet-B0

| 评估维度         | EfficientNet-B0 表现                               |
|-----------------|---------------------------------------------------|
| 模型体积         | **~16 MB** (ONNX 格式)，满足 < 20 MB 要求           |
| 推理速度         | CPU ~20 ms / GPU ~3 ms (224×224)                   |
| 分类精度         | 二分类 AUC-ROC > 0.99（充足训练数据下）               |
| 预训练权重       | ImageNet1K 预训练，迁移效果优秀                       |
| 导出支持         | PyTorch → ONNX 导出，完全兼容 ONNXRuntime            |

### 4.2 架构细节

```
输入图像 (3×224×224)
    │
    ▼
EfficientNet-B0 backbone（ImageNet 预训练）
    │
    ▼ 1280-d 特征向量
    │
Dropout(0.3) → Linear(1280, 1)
    │
    ▼ 单个 logit
sigmoid(logit) = P(fake)
```

| 组件        | 说明                                              |
|------------|--------------------------------------------------|
| Backbone   | EfficientNet-B0（ImageNet1K_V1 预训练权重）         |
| Head       | Dropout(0.3) + Linear(1280→1)                     |
| 输出       | 单 logit，sigmoid 后为 P(fake)                     |
| 损失函数   | BCEWithLogitsLoss + 正负样本加权 (pos_weight)       |
| 预处理     | Resize 224×224 → ToTensor → ImageNet Normalize     |

---

## 5. 数据集放置位置

### 5.1 宿主机路径与目录结构

```
/data/ai_platform/datasets/desktop_recapture_detect/
├── real/                        # 真实肖像照片
│   ├── person001.jpg
│   ├── person002.jpg
│   └── ...
├── fake/                        # 自动生成 + 手动翻拍（generate_fake.py 输出目录）
│   ├── person001_fake_viewer_blank_0.jpg
│   ├── person001_fake_desktop_1.jpg
│   ├── manual_screenshot01.jpg
│   └── ...
├── desktop_screen/              # 桌面截图模板
│   ├── win11_desktop.png
│   ├── macos_desktop.png
│   └── ...
├── pic_viewer/                  # 空白查看器模板
│   ├── win_photos_blank.png
│   └── ...
├── pic_viewer_temp2/            # 带图查看器模板
│   ├── win_photos_with_image.png
│   └── ...
└── desktop_screen_temp/         # 手动翻拍截图（可选，直接拷贝到 fake/）
    ├── manual_fake01.jpg
    └── ...
```

### 5.2 容器内映射

| 宿主机路径                                                | 容器内路径                                        |
|---------------------------------------------------------|--------------------------------------------------|
| `/data/ai_platform/datasets/desktop_recapture_detect/`  | `/workspace/datasets/desktop_recapture_detect/`   |

```yaml
# docker-compose.yml 卷挂载配置
volumes:
  - /data/ai_platform/datasets:/workspace/datasets
```

---

## 6. 完整操作流程

### 6.1 步骤 1：准备素材

在宿主机上创建数据集目录并放入素材：

```bash
# 创建目录结构
mkdir -p /data/ai_platform/datasets/desktop_recapture_detect/{real,fake,desktop_screen,pic_viewer,pic_viewer_temp2,desktop_screen_temp}

# 将真实肖像拷贝到 real/ 目录
cp /path/to/real_portraits/*.jpg /data/ai_platform/datasets/desktop_recapture_detect/real/

# 将桌面截图模板拷贝到 desktop_screen/ 目录
cp /path/to/desktop_screenshots/*.png /data/ai_platform/datasets/desktop_recapture_detect/desktop_screen/

# 将空白查看器模板拷贝到 pic_viewer/ 目录
cp /path/to/viewer_blank/*.png /data/ai_platform/datasets/desktop_recapture_detect/pic_viewer/

# 将带图查看器模板拷贝到 pic_viewer_temp2/ 目录
cp /path/to/viewer_with_image/*.png /data/ai_platform/datasets/desktop_recapture_detect/pic_viewer_temp2/

# （可选）将手动翻拍截图拷贝到 desktop_screen_temp/ 目录
cp /path/to/manual_fakes/*.jpg /data/ai_platform/datasets/desktop_recapture_detect/desktop_screen_temp/
```

验证素材数量：

```bash
echo "Real portraits:     $(ls /data/ai_platform/datasets/desktop_recapture_detect/real/ | wc -l)"
echo "Desktop templates:  $(ls /data/ai_platform/datasets/desktop_recapture_detect/desktop_screen/ | wc -l)"
echo "Viewer blank:       $(ls /data/ai_platform/datasets/desktop_recapture_detect/pic_viewer/ | wc -l)"
echo "Viewer with image:  $(ls /data/ai_platform/datasets/desktop_recapture_detect/pic_viewer_temp2/ | wc -l)"
echo "Manual fakes:       $(ls /data/ai_platform/datasets/desktop_recapture_detect/desktop_screen_temp/ | wc -l)"
```

### 6.2 步骤 2：生成假样本

**访问地址：** `http://<服务器IP>:8001/#/jobs`

点击 **"新建训练任务"**，选择脚本 `generate_fake.py`，或在训练容器内手动执行：

```bash
# 进入训练容器
docker compose exec train bash

# 切换到脚本目录
cd /app/scripts/desktop_recapture_detect/

# 生成假样本
python generate_fake.py \
    --dataset /workspace/datasets/desktop_recapture_detect/ \
    --config config.json
```

**可选操作：**

```bash
# 预览模式 — 生成少量样本到 /tmp，确认效果
python generate_fake.py \
    --dataset /workspace/datasets/desktop_recapture_detect/ \
    --preview

# 清除旧输出后重新生成
python generate_fake.py \
    --dataset /workspace/datasets/desktop_recapture_detect/ \
    --config config.json \
    --clear-output

# 自定义每张肖像生成的变体数
python generate_fake.py \
    --dataset /workspace/datasets/desktop_recapture_detect/ \
    --config config.json \
    --variants 4
```

**生成器工作原理：**

| 合成模式         | 权重   | 说明                                              |
|-----------------|--------|--------------------------------------------------|
| `viewer_blank`  | 0.45   | 真人肖像粘贴到空白查看器模板的客户区                  |
| `viewer_real`   | 0.35   | 真人肖像粘贴到带图查看器模板的低边缘区域               |
| `desktop`       | 0.20   | 真人肖像放入桌面截图上的模拟窗口中（含标题栏+阴影）     |

生成器会自动检测模板中的粘贴区域（灰色客户区检测 → 低边缘检测 → 中心区域回退），
然后将肖像以 letterbox 方式缩放粘贴，并添加 JPEG 压缩模拟。

**生成完成后验证：**

```bash
echo "Fake samples: $(ls /workspace/datasets/desktop_recapture_detect/fake/ | wc -l)"
echo "Real samples: $(ls /workspace/datasets/desktop_recapture_detect/real/ | wc -l)"
```

> ⚠️ **建议：** 先用 `--preview` 预览确认生成质量，再执行正式生成。fake 与 real 样本数建议比例 1:1 ~ 2:1。

### 6.3 步骤 3：模型训练

**访问地址：** `http://<服务器IP>:8001/#/jobs`

点击 **"新建训练任务"**，填写参数：

| 字段             | 值                                                  |
|-----------------|-----------------------------------------------------|
| 任务名称         | `desktop_recapture_detect_train_v1.0`                |
| 能力选择         | `desktop_recapture_detect`                           |
| 数据集路径       | `/workspace/datasets/desktop_recapture_detect`       |
| 训练轮次         | Phase 1: 5 + Phase 2: 25（由 config.json 控制）       |
| 批大小 (batch)   | `32`                                                 |
| 图像尺寸 (imgsz) | `224`                                                |
| GPU 设备         | `auto`                                               |

或在训练容器内手动执行：

```bash
cd /app/scripts/desktop_recapture_detect/

python train.py \
    --config config.json \
    --dataset /workspace/datasets/desktop_recapture_detect/ \
    --output /workspace/models/desktop_recapture_detect/v1.0.0/ \
    --version 1.0.0
```

**训练过程说明：**

| 阶段     | 轮数 | 训练内容                                | 学习率             |
|---------|------|----------------------------------------|-------------------|
| Phase 1 | 5    | 冻结 EfficientNet-B0 backbone，仅训练分类头 | `lr` (默认 1e-3)  |
| Phase 2 | 25   | 解冻所有参数全量微调                      | `lr × 0.1` + CosineAnnealing |

- 早停策略：连续 10 个 epoch 验证集 AUC-ROC 无提升则停止
- 数据集自动按源图分组切分（避免同源肖像泄漏到训练集和验证集）
- 正负样本权重自动计算 (`pos_weight = n_real / n_fake`)

**训练产出物：**

```
/workspace/models/desktop_recapture_detect/v1.0.0/
├── best.pth    # 验证集最佳 checkpoint
└── last.pth    # 最后一个 epoch checkpoint
```

### 6.4 步骤 4：模型评估

```bash
cd /app/scripts/desktop_recapture_detect/

python evaluate.py \
    --config config.json \
    --dataset /workspace/datasets/desktop_recapture_detect/ \
    --checkpoint /workspace/models/desktop_recapture_detect/v1.0.0/best.pth
```

输出指标示例：

```
=======================================================
Samples  : 120  (real=60  fake=60)
Accuracy : 0.9833
Precision: 0.9836
Recall   : 0.9833
F1 Score : 0.9835
AUC-ROC  : 0.9978

Confusion Matrix  (rows=actual  cols=predicted)
  Labels: 0=real  1=fake
[[59  1]
 [ 1 59]]

Classification Report:
              precision    recall  f1-score   support
        real       0.98      0.98      0.98        60
        fake       0.98      0.98      0.98        60
    accuracy                           0.98       120
```

> 📌 **达标标准：** AUC-ROC > 0.98，F1 > 0.96。若不达标，参考[常见问题 Q1](#q1-训练精度不达标怎么办)。

### 6.5 步骤 5：ONNX 导出

```bash
cd /app/scripts/desktop_recapture_detect/

python export.py \
    --output /workspace/models/desktop_recapture_detect/v1.0.0/ \
    --version 1.0.0
```

可指定自定义 checkpoint：

```bash
python export.py \
    --output /workspace/models/desktop_recapture_detect/v1.0.0/ \
    --version 1.0.0 \
    --checkpoint /workspace/models/desktop_recapture_detect/v1.0.0/best.pth
```

**导出产出物：**

```
/workspace/models/desktop_recapture_detect/v1.0.0/
├── model.onnx          # ONNX 推理模型
├── preprocess.json     # 预处理配置（resize、normalize 参数）
├── labels.json         # 类别标签映射
└── manifest.json       # 模型元数据（能力名、版本、阈值等）
```

### 6.6 步骤 6：模型测试

**访问地址：** `http://<服务器IP>:8002`

**单图测试：** 选择能力 `desktop_recapture_detect` → 上传图像 → 查看分类结果、置信度及推理耗时。

**批量测试：** 切换到"批量测试"选项卡，设置验证集路径，查看 Accuracy、AUC-ROC、F1 及平均推理时间等评测指标。

**推理结果字段说明：**

| 字段              | 类型    | 含义                                    |
|------------------|--------|----------------------------------------|
| `is_fake`        | bool   | 是否为翻拍（`true` = 翻拍，`false` = 真实）|
| `label`          | string | `"real"` 或 `"fake"`                    |
| `score_real`     | float  | 真实肖像概率 P(real)                     |
| `score_fake`     | float  | 翻拍概率 P(fake)                         |

### 6.7 步骤 7：授权管理

**访问地址：** `http://<服务器IP>:8003`

点击 **"生成密钥对"**，填写：
- 客户名称
- 能力列表：`["desktop_recapture_detect"]`
- 有效期及设备绑定（可选）

系统生成公钥（嵌入推理库）、私钥（签发授权文件）和 `license.dat`（部署到客户端）。

### 6.8 步骤 8：推理库编译

**访问地址：** `http://<服务器IP>:8004`

| 字段             | 值                             |
|-----------------|-------------------------------|
| 能力选择         | `desktop_recapture_detect`      |
| 目标平台         | `linux_x86_64`                  |
| 编译类型         | `release`                       |
| 推理后端         | `onnxruntime`                   |

编译产出物：

```
desktop_recapture_detect_linux_x86_64_release_v1.0.tar.gz
├── lib/libdesktop_recapture_detect.so   # 推理动态库
├── include/desktop_recapture_detect.h   # C/C++ 头文件
├── models/desktop_recapture_detect.onnx # 加密模型文件
└── config/config.json                   # 推理配置
```

### 6.9 步骤 9：生产部署

```bash
cd /data/ai_platform/prod
docker-compose -f docker-compose.prod.yml up -d
```

**访问地址：** `http://<服务器IP>:8080`

```bash
# 健康检查
curl -s http://localhost:8080/health
# {"status":"healthy","capabilities":["desktop_recapture_detect"],"version":"1.0.0"}
```

### 6.10 步骤 10：微调迭代

```
收集新样本 ──▶ 更新模板库 ──▶ 重新生成假样本 ──▶ 增量训练 ──▶ 回归测试 ──▶ 版本发布
    │                                                                    │
    └──────────────────────── 持续循环 ◀──────────────────────────────────┘
```

- 添加新的桌面截图、查看器模板到对应目录
- 补充更多真实肖像到 `real/` 目录
- 重新执行 `generate_fake.py` 生成更丰富的假样本
- 基于上一版本 `best.pth` 继续训练（可适当减少 epochs）
- 确保新版本在原验证集上指标不回退
- 更新版本号（v1.0 → v1.1）后重新导出、编译、部署

---

## 7. API 调用示例

### 7.1 单图推理

```bash
curl -X POST http://<服务器IP>:8080/api/v1/desktop_recapture_detect/predict \
    -H "Authorization: Bearer <your_api_key>" \
    -F "image=@/path/to/test.jpg"
```

**响应示例：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "is_fake": true,
        "label": "fake",
        "score_real": 0.0268,
        "score_fake": 0.9732,
        "inference_time_ms": 18.5
    }
}
```

### 7.2 Base64 编码推理

```bash
curl -X POST http://<服务器IP>:8080/api/v1/desktop_recapture_detect/predict \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your_api_key>" \
    -d '{"image_base64": "<base64_data>"}'
```

### 7.3 响应字段说明

| 字段              | 类型    | 含义                                        |
|------------------|--------|---------------------------------------------|
| `is_fake`        | bool   | 是否为翻拍（`true` = 桌面翻拍，`false` = 真人） |
| `label`          | string | `"real"` 或 `"fake"`                         |
| `score_real`     | float  | P(real)，范围 [0, 1]                          |
| `score_fake`     | float  | P(fake)，范围 [0, 1]                          |
| `inference_time_ms` | float | 推理耗时（毫秒）                              |

### 7.4 判定阈值

默认阈值：**0.5**（P(fake) ≥ 0.5 判定为翻拍）

| 场景             | 推荐阈值 | 说明                              |
|-----------------|---------|----------------------------------|
| 平衡精度与召回   | 0.5     | 默认值，适用于大多数场景             |
| 高安全场景       | 0.3     | 降低阈值提高对翻拍的召回率（更敏感）   |
| 低误判场景       | 0.7     | 提高阈值减少误判（更保守）            |

---

## 8. 训练超参数说明

### 8.1 完整配置文件 (config.json)

```json
{
    "capability": "desktop_recapture_detect",
    "capability_name_cn": "桌面翻拍检测",
    "model_arch": "efficientnet_b0",
    "input_size": [224, 224],
    "batch_size": 32,
    "lr": 1e-3,
    "lr_min": 1e-5,
    "weight_decay": 1e-4,
    "phase1_epochs": 5,
    "phase2_epochs": 25,
    "early_stopping_patience": 10,
    "train_ratio": 0.8,
    "device": "auto",
    "classes": ["real", "fake"],
    "num_classes": 2,
    "preprocessing": {
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "scale": 0.00392156862745098,
        "normalize": true,
        "color_format": "RGB"
    },
    "generate": {
        "variants_per_image": 2,
        "seed": 42,
        "include_manual_fake": true,
        "clear_output": false,
        "mode_weights": {
            "viewer_blank": 0.45,
            "viewer_real": 0.35,
            "desktop": 0.20
        }
    }
}
```

### 8.2 关键参数调优建议

| 参数                        | 默认值   | 调优建议                                       |
|---------------------------|---------|------------------------------------------------|
| `phase1_epochs`           | 5       | 一般无需修改；数据量极小时可增至 10                |
| `phase2_epochs`           | 25      | 数据量大（>5000 样本）可增至 50                    |
| `batch_size`              | 32      | GPU 显存不足时降至 16 或 8；显存充足可增至 64       |
| `lr`                      | 1e-3    | Phase 1 学习率，Phase 2 自动降为 1e-4              |
| `lr_min`                  | 1e-5    | 余弦退火最低学习率                                |
| `early_stopping_patience` | 10      | 连续 N 轮无改善则停止，数据量大时可增至 15          |
| `train_ratio`             | 0.8     | 80% 训练 / 20% 验证，数据量少时可调至 0.9          |
| `input_size`              | 224     | 提高至 299 可略提精度，但推理变慢                   |
| `generate.variants_per_image` | 2   | 每张真实肖像生成 N 个假样本变体                     |

### 8.3 数据增强

训练阶段自动应用以下增强：

| 增强方式               | 参数                               |
|-----------------------|-----------------------------------|
| RandomResizedCrop     | scale=(0.7, 1.0), size=224        |
| RandomHorizontalFlip  | p=0.5                             |
| RandomRotation         | degrees=10                        |
| ColorJitter            | brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05 |
| ImageNet Normalize     | mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225] |

---

## 9. 假样本生成详解

### 9.1 生成原理

`generate_fake.py` 通过将真实肖像合成到桌面/查看器模板上，模拟翻拍场景：

```
真实肖像 + 模板 ──▶ 自动检测粘贴区域 ──▶ 肖像缩放+粘贴 ──▶ JPEG 压缩模拟 ──▶ 假样本
```

### 9.2 三种合成模式

#### 模式一：viewer_blank（空白查看器）

```
┌──────────────────────────────┐
│  照片浏览器（空白背景 ~245 灰） │
│  ┌────────────────────┐      │
│  │                    │      │
│  │    ← 真实肖像 →    │      │
│  │   (letterbox缩放)  │      │
│  │                    │      │
│  └────────────────────┘      │
└──────────────────────────────┘
```

- 自动检测灰色客户区（RGB 235-255，spread ≤ 10）
- 肖像以 letterbox 方式缩放至检测到的区域

#### 模式二：viewer_real（带图查看器）

- 类似 viewer_blank，但模板中已有一张图片
- 使用低边缘检测寻找平坦区域作为粘贴位置

#### 模式三：desktop（桌面窗口）

```
┌──────────────────────────────────┐
│  桌面壁纸                         │
│      ┌─ ─ ─ ─ ─ ─ ─ ─ ─┐        │
│      │ 标题栏 (深灰)      │        │
│      ├───────────────────┤        │
│      │                   │        │
│      │   ← 真实肖像 →    │        │
│      │  (随机大小+位置)   │        │
│      │                   │        │
│      └───────────────────┘        │
│          ↑ 窗口阴影                │
└──────────────────────────────────┘
```

- 在桌面截图上叠加模拟窗口（含标题栏、边框、阴影）
- 窗口大小和位置随机

### 9.3 生成配置参数

| 参数                          | 默认值 | 说明                                         |
|------------------------------|-------|----------------------------------------------|
| `generate.variants_per_image` | 2     | 每张真实肖像生成假样本数量                       |
| `generate.seed`              | 42    | 随机种子，确保可重复                             |
| `generate.include_manual_fake`| true  | 是否将手动翻拍截图拷贝到 fake/                   |
| `generate.clear_output`      | false | 生成前是否清空 fake/ 目录                        |
| `generate.mode_weights`      | {...}  | 三种合成模式的权重分配                           |

### 9.4 最佳实践

1. **先预览后生成：** 先用 `--preview` 检查合成质量
2. **模板多样性：** 尽量包含不同操作系统、分辨率、浏览器的模板
3. **肖像多样性：** 包含不同肤色、性别、年龄、光照、角度的人像
4. **样本平衡：** fake 和 real 数量保持 1:1 到 2:1
5. **手动补充：** `desktop_screen_temp/` 中放入实际翻拍截图，增加真实感

---

## 10. 常见问题

### Q1: 训练精度不达标怎么办？

| 原因                  | 解决方法                                           |
|----------------------|---------------------------------------------------|
| 样本量不足            | 增加真实肖像到 500+ 张，增大 `variants_per_image`     |
| 模板单一              | 补充更多桌面截图和查看器模板                           |
| 训练轮次不够          | 增大 `phase2_epochs` 至 50                           |
| 数据泄漏              | 确认 real/ 中没有与假样本来源相同的图片混入验证集        |

### Q2: 假样本生成失败怎么办？

| 错误信息                         | 原因              | 解决方法                              |
|--------------------------------|------------------|---------------------------------------|
| `No real portraits found`       | real/ 目录为空    | 将真实肖像放入 real/ 目录               |
| `No generation templates found` | 模板目录均为空     | 至少提供一种模板到对应目录               |
| 大量 failures                   | 图片文件损坏       | 检查并删除无法打开的图片文件             |

### Q3: GPU 显存不足怎么办？

降低 `batch_size`（32→16→8）；`input_size` 保持 224 不建议再降低；使用混合精度训练（如需，可修改 train.py 添加 `torch.cuda.amp` 支持）。

### Q4: 如何增量训练？

目前需手动加载上一版本 checkpoint 的 `model_state`。建议流程：
1. 新增素材到数据集目录
2. 重新执行 `generate_fake.py`
3. 执行 `train.py`（自动从头训练，但 ImageNet 预训练权重保障了良好起点）

### Q5: 如何在 Windows 平台使用推理库？

在编译服务 (`:8004`) 中选择 `windows_x64` 作为目标平台，产出 DLL 格式，通过 C/C++ 头文件或 JNI 桥接调用。

### Q6: C++ 推理插件如何工作？

`desktop_recapture_detect.cpp` 使用 ONNXRuntime C API：
1. 加载 `model.onnx` 和 `preprocess.json`
2. 输入图像 resize 至 224×224 → BGR2RGB → /255.0 → normalize
3. 推理得到单个 logit → sigmoid = P(fake)
4. 返回 `{"is_fake": bool, "label": "...", "score_real": ..., "score_fake": ...}`

---

## 11. 性能基准

### 11.1 分类精度（平衡验证集）

| 指标         | 数值          | 说明                              |
|-------------|--------------|----------------------------------|
| Accuracy    | **98.3%**    | 二分类准确率                        |
| Precision   | **98.4%**    | 假样本预测精确率                     |
| Recall      | **98.3%**    | 假样本召回率                         |
| F1 Score    | **98.3%**    | 精确率与召回率的调和平均              |
| AUC-ROC     | **0.998**    | ROC 曲线下面积                      |

> 📌 以上数值基于 200 张真实肖像 + 400 张合成假样本的测试结果，实际精度视数据质量和数量而异。

### 11.2 推理速度（输入 224×224，单位 ms）

| 硬件平台                     | FP32  | 说明                |
|-----------------------------|-------|---------------------|
| Intel i7-12700 (CPU)        | 18.5  | ONNXRuntime CPU     |
| NVIDIA RTX 3060 (GPU)       | 3.2   | ONNXRuntime CUDA    |
| NVIDIA RTX 3090 (GPU)       | 2.1   | ONNXRuntime CUDA    |

### 11.3 模型体积

| 格式               | 大小      | 说明                    |
|-------------------|----------|------------------------|
| PyTorch (.pth)    | ~16 MB   | 训练 checkpoint         |
| ONNX (.onnx)     | ~16 MB   | 通用推理格式              |

---

> 📌 **文档维护说明：** 本文档随能力版本迭代同步更新。如有疑问，请联系 AI 平台研发团队。
>
> | 版本    | 日期        | 修改内容         | 作者       |
> |--------|-----------|-----------------|-----------|
> | v1.0   | 2026-03-30 | 初始版本发布      | AI 平台团队 |
