# AI 能力平台 —— 人脸检测能力操作指南

**北京爱知之星科技股份有限公司 (Agile Star)**
**版本:** v1.0 | **日期:** 2026-03-30 | **文档编号:** CAP-FACE-001
**官网：[agilestar.cn](https://agilestar.cn)**

---

## 目录

1. [概述](#1-概述)
2. [性能指标要求](#2-性能指标要求)
3. [推荐数据集](#3-推荐数据集)
4. [推荐框架](#4-推荐框架)
5. [数据集放置位置](#5-数据集放置位置)
6. [完整操作流程](#6-完整操作流程)
7. [API 调用示例](#7-api-调用示例)
8. [训练超参数说明](#8-训练超参数说明)
9. [遮挡检测说明](#9-遮挡检测说明)
10. [常见问题](#10-常见问题)
11. [性能基准](#11-性能基准)

---

## 1. 概述

### 1.1 能力简介

**人脸检测 (face_detect)** 是 AI 能力平台上线的首个视觉类 AI 能力，属于目标检测范畴。
该能力可对输入图像进行实时人脸定位，输出每张人脸的边界框坐标 (bounding box) 及置信度分数，
同时支持 **多人脸检测** 与 **遮挡人脸识别**。

### 1.2 核心特性

| 特性         | 描述                                                       |
|-------------|-----------------------------------------------------------|
| 多人脸检测   | 单图最多同时检测 **200+** 张人脸，适用于人群密集场景            |
| 遮挡检测     | 自动区分正常人脸 (`face`) 与遮挡人脸 (`occluded_face`)        |
| 多尺度适应   | 支持检测 **20×20 px** 到 **4096×4096 px** 范围内的人脸        |
| 跨平台部署   | 支持 Linux x86_64 / aarch64，Windows x64，含 Docker 与 SO 交付 |
| 轻量高效     | 模型体积 < 10 MB，CPU 推理 < 50 ms，GPU 推理 < 10 ms         |

### 1.3 全链路流程总览

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 数据集准备 │───▶│ 样本标注   │───▶│ 模型训练   │───▶│ 模型测试   │
│(WIDER FACE)│    │ (:8001)  │    │ (:8001)  │    │ (:8002)  │
└──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                ┌──────────┐    ┌──────────┐         │
                │ 生产部署   │◀───│ 推理库编译 │◀────────┘
                │ (:8080)  │    │ (:8004)  │
                └──────────┘    └─────┬────┘
                                ┌─────▼────┐
                                │ 授权管理   │
                                │ (:8003)  │
                                └──────────┘
```

---

## 2. 性能指标要求

| 指标              | 要求                 | 说明                              |
|------------------|---------------------|----------------------------------|
| 模型体积          | **< 10 MB**         | ONNX 格式，便于嵌入式与移动端部署    |
| 检测精度 (mAP@0.5)| **> 98%**           | 在 WIDER FACE Easy 子集上评测       |
| CPU 推理延迟      | **< 50 ms**         | Intel i7-12700，单张 640×640 图像   |
| GPU 推理延迟      | **< 10 ms**         | NVIDIA RTX 3060，单张 640×640 图像  |
| 最小检测人脸      | **20 × 20 px**      | 图像中人脸最小尺寸                  |
| 多人脸上限        | **≥ 200 张**        | 单图同时检测人脸数量                 |
| 遮挡检测准确率    | **> 95%**           | 遮挡面积 > 30% 时的分类准确率        |

---

## 3. 推荐数据集

### 3.1 主推荐：WIDER FACE

| 属性         | 详情                                                                |
|-------------|---------------------------------------------------------------------|
| 下载地址     | [http://shuoyang1213.me/WIDERFACE/](http://shuoyang1213.me/WIDERFACE/) |
| 图像总数     | **32,203** 张                                                       |
| 人脸标注总数  | **393,703** 个                                                      |
| 训练集       | 12,880 张图像 / 159,424 个标注                                       |
| 验证集       | 3,226 张图像 / 39,708 个标注                                         |
| 测试集       | 16,097 张图像 / 194,571 个标注                                       |
| 场景多样性   | 61 个事件类别（会议、游行、交通、运动等）                               |
| 标注信息     | 边界框 (x, y, w, h) + 遮挡/姿态/光照等属性                            |

下载文件：`WIDER_train.zip`、`WIDER_val.zip`、`WIDER_test.zip`、`wider_face_split.zip`（标注）

### 3.2 备选数据集：FDDB

| 属性         | 详情                                                   |
|-------------|-------------------------------------------------------|
| 全称         | Face Detection Data Set and Benchmark                  |
| 图像总数     | 2,845 张                                              |
| 人脸标注总数  | 5,171 个                                              |
| 标注格式     | 椭圆区域 (elliptical region)                           |
| 用途         | 可作为补充验证集或小规模快速实验数据集                    |

> ⚠️ **注意：** FDDB 数据规模较小，建议仅用于快速验证，正式训练请使用 WIDER FACE。

---

## 4. 推荐框架

### 4.1 框架选型：Ultralytics YOLOv8n

| 评估维度         | YOLOv8n 表现                                        |
|-----------------|---------------------------------------------------- |
| 模型体积         | **~6 MB** (ONNX 格式)，满足 < 10 MB 要求             |
| 推理速度         | CPU ~30 ms / GPU ~5 ms (640×640)，远优于性能指标要求   |
| 检测精度         | 人脸场景微调后 mAP@0.5 > 98%                          |
| 多人脸原生支持   | YOLO 架构天然支持单图多目标检测，无需额外后处理          |
| 社区活跃度       | GitHub 40k+ stars，持续更新，文档完善                   |
| 导出支持         | 原生支持 ONNX / TensorRT / OpenVINO 等格式导出         |

### 4.2 选型对比

| 框架              | 模型体积   | CPU 延迟  | GPU 延迟 | mAP@0.5 | 推荐度 |
|------------------|-----------|----------|---------|---------|-------|
| **YOLOv8n**      | ~6 MB     | ~30 ms   | ~5 ms   | > 98%   | ⭐⭐⭐⭐⭐ |
| RetinaFace       | ~30 MB    | ~80 ms   | ~15 ms  | > 97%   | ⭐⭐⭐   |
| MTCNN            | ~2 MB     | ~100 ms  | ~20 ms  | > 94%   | ⭐⭐    |
| BlazeFace        | ~0.5 MB   | ~10 ms   | ~3 ms   | > 90%   | ⭐⭐    |
| SCRFD            | ~10 MB    | ~40 ms   | ~8 ms   | > 97%   | ⭐⭐⭐⭐  |

> 💡 **总结：** YOLOv8n 在体积、速度、精度三者之间取得了最佳平衡，且与平台 ONNX 推理链路完全兼容。

---

## 5. 数据集放置位置

### 5.1 宿主机路径与目录结构（YOLO 格式）

```
/data/ai_platform/datasets/face_detect/
├── dataset.yaml                 # 数据集配置文件
├── images/
│   ├── train/                   # 训练集图像（~12,880 张）
│   └── val/                     # 验证集图像（~3,226 张）
├── labels/
│   ├── train/                   # 训练集标注（YOLO 格式 .txt）
│   └── val/                     # 验证集标注（YOLO 格式 .txt）
└── README.md                    # 数据集说明（可选）
```

### 5.2 dataset.yaml 配置

```yaml
path: /workspace/datasets/face_detect
train: images/train
val: images/val
nc: 2
names:
  0: face
  1: occluded_face
```

### 5.3 YOLO 标注格式

每张图像对应一个同名 `.txt` 文件，每行格式：`<class_id> <x_center> <y_center> <width> <height>`（坐标均为归一化值 [0.0, 1.0]）

示例：`0 0.4521 0.3125 0.0842 0.1253`（class_id: 0=face, 1=occluded_face）

### 5.4 容器内映射

| 宿主机路径                                  | 容器内路径                            |
|--------------------------------------------|--------------------------------------|
| `/data/ai_platform/datasets/face_detect/`  | `/workspace/datasets/face_detect/`   |

```yaml
# docker-compose.yml 卷挂载配置
volumes:
  - /data/ai_platform/datasets:/workspace/datasets
```

---

## 6. 完整操作流程

### 6.1 步骤 1：下载数据集

```bash
mkdir -p /data/ai_platform/datasets/face_detect/raw
cd /data/ai_platform/datasets/face_detect/raw

wget http://shuoyang1213.me/WIDERFACE/WIDER_train.zip
wget http://shuoyang1213.me/WIDERFACE/WIDER_val.zip
wget http://shuoyang1213.me/WIDERFACE/wider_face_split.zip

unzip WIDER_train.zip && unzip WIDER_val.zip && unzip wider_face_split.zip
```

### 6.2 步骤 2：转换数据格式

使用平台提供的脚本将 WIDER FACE 原始标注转换为 YOLO 格式：

```bash
python scripts/convert_widerface.py \
    --input_dir /workspace/datasets/face_detect/raw \
    --output_dir /workspace/datasets/face_detect \
    --format yolo \
    --occlusion_threshold 0.3
```

| 参数                    | 说明                                      | 默认值  |
|------------------------|------------------------------------------|--------|
| `--input_dir`          | WIDER FACE 原始数据目录                    | 必填    |
| `--output_dir`         | YOLO 格式输出目录                          | 必填    |
| `--format`             | 输出格式 (`yolo` / `coco` / `voc`)         | `yolo` |
| `--occlusion_threshold`| 遮挡比例阈值，超过此值标记为 occluded_face   | `0.3`  |

### 6.3 步骤 3：样本标注

**访问地址：** `http://<服务器IP>:8001/#/annotations`

1. 点击 **"新建标注项目"**，填写项目信息：

| 字段             | 值                                  |
|-----------------|-------------------------------------|
| 项目名称         | `face_detect_v1`                     |
| 能力类型         | `object_detection`                   |
| 标签列表         | `["face", "occluded_face"]`          |
| 数据集路径       | `/workspace/datasets/face_detect/images/train` |

2. 使用矩形框工具标注人脸区域，为每个框选择类别：
   - **face** — 人脸清晰可见（遮挡面积 ≤ 30%）
   - **occluded_face** — 人脸被部分遮挡（遮挡面积 > 30%）

3. 标注规范：框选完整人脸区域（额头到下巴），框边紧贴轮廓；侧脸可见面积 > 50% 时标注；不标注背影、极小人脸（< 20×20 px）和绘画/雕塑中的人脸。

### 6.4 步骤 4：导出标注

1. 在标注项目页面点击 **"导出标注"**
2. 导出格式选择 **YOLO**，路径设为 `/workspace/datasets/face_detect/labels`
3. 验证导出结果：

```bash
ls /workspace/datasets/face_detect/labels/train/ | wc -l  # 期望：12880
ls /workspace/datasets/face_detect/labels/val/ | wc -l    # 期望：3226
```

### 6.5 步骤 5：模型训练

**访问地址：** `http://<服务器IP>:8001/#/jobs`

点击 **"新建训练任务"**，填写参数：

| 字段             | 值                                          |
|-----------------|---------------------------------------------|
| 任务名称         | `face_detect_train_v1.0`                     |
| 能力选择         | `face_detect`                                |
| 数据集路径       | `/workspace/datasets/face_detect`            |
| 基础模型         | `yolov8n.pt`（预训练权重）                    |
| 训练轮次 (epochs)| `100`                                        |
| 批大小 (batch)   | `16`                                         |
| 图像尺寸 (imgsz) | `640`                                        |
| 学习率 (lr0)     | `0.01`                                       |
| GPU 设备         | `0`                                          |

提交后在任务列表中查看训练进度，训练完成后自动保存最佳模型（`best.pt` / `best.onnx`）。

### 6.6 步骤 6：模型测试

**访问地址：** `http://<服务器IP>:8002`

**单图测试：** 选择能力 `face_detect` → 上传图像 → 查看检测框、类别、置信度及推理耗时。

**批量测试：** 切换到"批量测试"选项卡，设置验证集与标注路径，查看 mAP@0.5、Precision、Recall 及平均推理时间等评测指标。

### 6.7 步骤 7：授权管理

**访问地址：** `http://<服务器IP>:8003`

点击 **"生成密钥对"**，填写客户名称、能力列表 `["face_detect"]`、有效期及设备绑定（可选）。系统生成公钥（嵌入推理库）、私钥（签发授权文件）和 `license.dat`（部署到客户端）。

### 6.8 步骤 8：推理库编译

**访问地址：** `http://<服务器IP>:8004`

| 字段             | 值                      |
|-----------------|------------------------|
| 能力选择         | `face_detect`            |
| 目标平台         | `linux_x86_64`           |
| 编译类型         | `release`                |
| 推理后端         | `onnxruntime`            |

编译产出物：

```
face_detect_linux_x86_64_release_v1.0.tar.gz
├── lib/libface_detect.so       # 推理动态库
├── include/face_detect.h       # C/C++ 头文件
├── models/face_detect.onnx     # 加密模型文件
└── config/config.json          # 推理配置
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
# {"status":"healthy","capabilities":["face_detect"],"version":"1.0.0"}
```

### 6.10 步骤 10：微调迭代

```
收集新样本 ──▶ 补充标注 ──▶ 增量训练 ──▶ 回归测试 ──▶ 版本发布
    │                                                    │
    └────────────────── 持续循环 ◀──────────────────────┘
```

基于上一版本权重继续训练（epochs 可减至 50），确保新版本在原验证集上指标不回退，更新版本号（v1.0 → v1.1）后重新编译部署。

---

## 7. API 调用示例

### 7.1 单图推理

```bash
curl -X POST http://<服务器IP>:8080/api/v1/face_detect/predict \
    -H "Authorization: Bearer <your_api_key>" \
    -F "image=@/path/to/photo.jpg" \
    -F "conf_threshold=0.5" \
    -F "iou_threshold=0.45"
```

**响应示例：**

```json
{
    "code": 0, "message": "success",
    "data": {
        "image_width": 1920, "image_height": 1080, "inference_time_ms": 28.3,
        "detections": [
            { "class": "face", "confidence": 0.9823,
              "bbox": { "x_min": 245, "y_min": 120, "x_max": 380, "y_max": 310 } },
            { "class": "occluded_face", "confidence": 0.8756,
              "bbox": { "x_min": 620, "y_min": 200, "x_max": 735, "y_max": 365 } }
        ],
        "total_faces": 2
    }
}
```

### 7.2 Base64 编码推理

```bash
curl -X POST http://<服务器IP>:8080/api/v1/face_detect/predict \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your_api_key>" \
    -d '{"image_base64": "<base64_data>", "conf_threshold": 0.5, "iou_threshold": 0.45}'
```

---

## 8. 训练超参数说明

```json
{
    "capability": "face_detect",
    "model": {
        "architecture": "yolov8n", "pretrained": "yolov8n.pt",
        "input_size": 640, "num_classes": 2,
        "class_names": ["face", "occluded_face"]
    },
    "training": {
        "epochs": 100, "batch_size": 16, "learning_rate": 0.01,
        "optimizer": "SGD", "momentum": 0.937, "weight_decay": 0.0005,
        "warmup_epochs": 3, "cos_lr": true, "patience": 50
    },
    "augmentation": {
        "hsv_h": 0.015, "hsv_s": 0.7, "hsv_v": 0.4,
        "translate": 0.1, "scale": 0.5, "fliplr": 0.5,
        "mosaic": 1.0, "mixup": 0.0
    },
    "inference": {
        "conf_threshold": 0.5, "iou_threshold": 0.45, "max_detections": 300
    }
}
```

**关键参数调优建议：**

| 参数                | 推荐值    | 调优建议                              |
|--------------------|----------|--------------------------------------|
| `epochs`           | 100      | 数据量大可降至 50，数据量小可增至 200     |
| `batch_size`       | 16       | GPU 显存不足时降至 8，充足时增至 32      |
| `learning_rate`    | 0.01     | 微调时建议降至 0.001                    |
| `input_size`       | 640      | 检测小人脸可增至 1280，速度优先可降至 320 |
| `patience`         | 50       | 验证集 mAP 连续 N 轮无提升则停止训练     |
| `conf_threshold`   | 0.5      | 高召回场景降至 0.25，高精度场景升至 0.7   |
| `iou_threshold`    | 0.45     | 密集人脸场景可提高至 0.6                 |

---

## 9. 遮挡检测说明

### 9.1 类别定义

| 类别             | 标签             | 定义                                     |
|-----------------|-----------------|------------------------------------------|
| 正常人脸         | `face`           | 人脸清晰可见，遮挡面积 **≤ 30%**           |
| 遮挡人脸         | `occluded_face`  | 人脸被部分遮挡，遮挡面积 **> 30%**          |

### 9.2 遮挡类型与处理

| 遮挡类型     | 示例                         | 检测策略              |
|-------------|-----------------------------|-----------------------|
| 物体遮挡     | 手、书本、杯子挡住部分脸部     | 标记为 occluded_face  |
| 人脸重叠     | 人群中前后人脸互相遮挡         | 分别检测并标记遮挡状态  |
| 佩戴物遮挡   | 口罩、墨镜、帽子               | 口罩标记为 occluded_face，其余视面积而定 |
| 边缘截断     | 人脸在图像边缘被截断           | 可见面积 > 50% 时标注  |

### 9.3 NMS IOU 阈值策略

| 场景             | 推荐 IOU 阈值 | 说明                                  |
|-----------------|--------------|--------------------------------------|
| 常规场景         | 0.45          | 默认值，适用于人脸间距较大的场景          |
| 密集人群         | 0.60          | 防止相邻人脸被误合并                     |
| 极端密集         | 0.70          | 演唱会、游行等超密集场景                  |

### 9.4 遮挡判定规则

```
遮挡比例 = 被遮挡像素面积 / 人脸总面积 × 100%

├── ≤ 30%         →  标记为 face
├── 30% ~ 80%     →  标记为 occluded_face
└── > 80%         →  不标注（视为不可见）
```

---

## 10. 常见问题

### Q1: 训练时 GPU 显存不足怎么办？

降低 `batch_size`（16→8→4）或 `input_size`（640→480→320）；启用混合精度（`"amp": true`）；使用梯度累积（`"accumulate": 4`）。

### Q2: 数据集格式转换报错怎么办？

| 错误信息                           | 原因              | 解决方法                           |
|-----------------------------------|------------------|-----------------------------------|
| `FileNotFoundError: wider_face_*` | 原始文件路径不正确  | 检查 `--input_dir` 是否指向正确目录  |
| `ValueError: invalid bbox`        | 标注框坐标越界     | 添加 `--skip_invalid` 参数跳过异常  |
| `UnicodeDecodeError`              | 文件编码问题       | 确保系统 locale 为 UTF-8           |

### Q3: 训练精度达不到 98% 怎么办？

检查标注质量并清洗错误标注；增加 epochs 至 200；开启 mosaic+mixup 增强；将 input_size 提升至 1280；启用余弦退火 (`cos_lr: true`)。

### Q4: CPU 推理超过 50ms 怎么办？

确认硬件至少 Intel i5 及以上；开启 ONNX Runtime 图优化；推理时降低 input_size 至 480；使用 INT8 量化模型。

### Q5: 如何在 Windows 平台使用推理库？

在编译服务 (`:8004`) 中选择 `windows_x64` 作为目标平台，产出 DLL 格式，通过 C/C++ 头文件或 JNI 桥接调用。

### Q6: 低光照场景检测效果差怎么办？

加大训练时亮度增强（`hsv_v: 0.6`）；补充低光照样本；推理前做直方图均衡化预处理。

---

## 11. 性能基准

### 11.1 检测精度（WIDER FACE 验证集）

| 子集          | mAP@0.5  | mAP@0.5:0.95 | 说明                    |
|--------------|----------|--------------|------------------------|
| Easy         | 98.56%   | 78.23%       | 大尺寸、无遮挡人脸        |
| Medium       | 96.78%   | 72.45%       | 中等尺寸、轻度遮挡        |
| Hard         | 89.34%   | 58.67%       | 小尺寸、重度遮挡          |
| **加权平均**  | **95.12%** | **70.45%** | **按子集样本数加权**      |

### 11.2 推理速度（输入 640×640，单位 ms）

| 硬件平台                     | FP32  | FP16 | INT8 |
|-----------------------------|-------|------|------|
| Intel i7-12700 (CPU)        | 28.3  | -    | 18.5 |
| NVIDIA RTX 3060 (GPU)       | 4.7   | 3.2  | 2.1  |
| NVIDIA RTX 3090 (GPU)       | 3.1   | 2.0  | 1.3  |
| NVIDIA Jetson Xavier (Edge)  | 15.6  | 8.9  | 5.4  |

### 11.3 模型体积

| 格式               | 大小     | 说明                    |
|-------------------|---------|------------------------|
| PyTorch (.pt)     | 6.3 MB  | 训练与微调               |
| ONNX (.onnx)     | 6.2 MB  | 通用推理格式              |
| TensorRT (.engine)| 4.8 MB  | NVIDIA GPU 专用加速       |
| INT8 量化 (.onnx) | 2.1 MB  | 量化后，精度损失 < 1%     |

### 11.4 并发性能（生产环境 :8080）

| 部署配置                        | QPS  | 平均延迟 (ms) | P99 延迟 (ms) |
|-------------------------------|------|-------------|-------------|
| 单 CPU (i7-12700, 4 workers)  | 35   | 112         | 245         |
| 单 GPU (RTX 3060, 2 workers)  | 180  | 11          | 28          |
| 双 GPU (RTX 3060 × 2)         | 340  | 12          | 32          |

---

> 📌 **文档维护说明：** 本文档随能力版本迭代同步更新。如有疑问，请联系 AI 平台研发团队。
>
> | 版本    | 日期        | 修改内容         | 作者       |
> |--------|-----------|-----------------|-----------|
> | v1.0   | 2026-03-30 | 初始版本发布      | AI 平台团队 |
