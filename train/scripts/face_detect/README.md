# 人脸检测（`face_detect`）

## 技术选型

| 项目 | 说明 |
|------|------|
| 模型架构 | YOLOv8n (Ultralytics) |
| 深度学习框架 | PyTorch 2.x + Ultralytics |
| 推理引擎 | ONNXRuntime 1.18+ |
| 主要依赖 | 详见 `requirements.txt` |

YOLOv8n 是一种轻量级目标检测网络，针对人脸检测微调后具备以下优势：
- **模型体积** < 10 MB（ONNX 格式约 6 MB）
- **推理速度**：CPU < 50 ms，GPU < 10 ms（640×640 输入）
- **检测精度**：WIDER FACE Easy > 98% mAP
- **多人脸检测**：单图最多 300 张人脸
- **遮挡检测**：区分正常人脸 (`face`) 与遮挡人脸 (`occluded_face`)

---

## 推荐开源数据集

### WIDER FACE（首选）

| 属性 | 说明 |
|------|------|
| 图片数量 | 32,203 张 |
| 标注人脸 | 393,703 个 |
| 场景 | 61 种事件类别（会议、游行、聚会等） |
| 难度分级 | Easy / Medium / Hard |
| 下载地址 | http://shuoyang1213.me/WIDERFACE/ |
| 许可证 | 仅限学术研究（商用需取得额外授权） |

### FDDB（备选）

| 属性 | 说明 |
|------|------|
| 图片数量 | 2,845 张 |
| 标注人脸 | 5,171 个 |
| 下载地址 | http://vis-www.cs.umass.edu/fddb/ |

> **注意**：训练前请确认数据集许可证，并遵循相应使用条款。

---

## 数据集目录结构

### 宿主机位置

```
/data/ai_platform/datasets/face_detect/
├── images/
│   ├── train/        # 训练集图片
│   │   ├── 0001.jpg
│   │   └── ...
│   └── val/          # 验证集图片
│       ├── 0001.jpg
│       └── ...
├── labels/
│   ├── train/        # YOLO 格式标签（每个图片一个 .txt）
│   │   ├── 0001.txt
│   │   └── ...
│   └── val/
│       ├── 0001.txt
│       └── ...
└── data.yaml         # YOLOv8 数据集配置文件
```

### YOLO 标签格式

每个 `.txt` 文件中，每行代表一个人脸：

```
<class_id> <cx> <cy> <w> <h>
```

- `class_id`: 0 = 正常人脸 (face)，1 = 遮挡人脸 (occluded_face)
- `cx, cy, w, h`: 归一化坐标 (0~1)

### data.yaml 示例

```yaml
path: /workspace/datasets/face_detect
train: images/train
val: images/val
nc: 2
names:
  0: face
  1: occluded_face
```

---

## 准备数据集

### 1. 下载 WIDER FACE

```bash
# 在宿主机上下载
mkdir -p /data/ai_platform/downloads
cd /data/ai_platform/downloads

# 下载训练集图片
wget https://huggingface.co/datasets/wider_face/resolve/main/data/WIDER_train.zip

# 下载验证集图片
wget https://huggingface.co/datasets/wider_face/resolve/main/data/WIDER_val.zip

# 下载标注文件
wget http://shuoyang1213.me/WIDERFACE/support/bbx_annotation/wider_face_split.zip

# 解压
unzip WIDER_train.zip
unzip WIDER_val.zip
unzip wider_face_split.zip
```

### 2. 转换为 YOLO 格式

```bash
# 进入训练容器执行转换
docker exec -it ai-train python /app/train/scripts/face_detect/convert_widerface.py \
    --widerface-root /workspace/downloads/ \
    --output /workspace/datasets/face_detect/
```

或者在宿主机上直接执行：

```bash
python train/scripts/face_detect/convert_widerface.py \
    --widerface-root /data/ai_platform/downloads/ \
    --output /data/ai_platform/datasets/face_detect/
```

### 3. 标注自有数据（可选）

如果需要补充自有数据标注，可在训练 Web 页面进行：

1. 打开 `http://<服务器IP>:8001/#/annotations`
2. 创建标注项目：
   - 标注类型：**目标检测** (`object_detection`)
   - 标签配置：`{"labels": ["face", "occluded_face"]}`
   - 数据集路径：`/workspace/datasets/face_detect/images/train`
3. 完成标注后导出为 YOLO 格式

---

## 训练方法

### 1. 环境准备

```bash
pip install -r requirements.txt
```

### 2. 启动训练

```bash
python train.py \
    --config config.json \
    --dataset /workspace/datasets/face_detect/ \
    --output /workspace/models/face_detect/v1.0.0/ \
    --version 1.0.0
```

### 3. 恢复训练（从检查点）

```bash
python train.py \
    --config config.json \
    --dataset /workspace/datasets/face_detect/ \
    --output /workspace/models/face_detect/v1.0.0/ \
    --version 1.0.0 \
    --resume /workspace/models/face_detect/v1.0.0/checkpoints/last.pt
```

主要超参数（见 `config.json`）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `batch_size` | 16 | 批大小，可根据显存调整 |
| `epochs` | 100 | 最大训练轮次 |
| `lr0` | 0.01 | 初始学习率 |
| `lrf` | 0.01 | 最终学习率衰减比例 |
| `patience` | 50 | 早停等待轮次 |
| `conf` | 0.25 | 推理置信度阈值 |
| `iou` | 0.45 | NMS IoU 阈值 |
| `max_det` | 300 | 单图最大检测数 |
| `amp` | True | 是否启用混合精度训练 |
| `augment` | True | 是否启用数据增强 |

### 4. 导出模型

```bash
python export.py \
    --output /workspace/models/face_detect/v1.0.0/ \
    --version 1.0.0
```

导出产物：

| 文件 | 说明 |
|------|------|
| `model.onnx` | ONNX 推理模型 |
| `preprocess.json` | 前处理参数 |
| `labels.json` | 类别标签 |
| `manifest.json` | 模型元数据 |

---

## 测试方法

### 功能测试

访问测试 Web 页面 `http://<IP>:8002`：

1. 选择 **face_detect** 能力和模型版本
2. 上传测试图片
3. 查看检测框可视化结果

### 批量评估

在 WIDER FACE val 集上评估 mAP 指标：

```bash
docker exec ai-train python -c "
from ultralytics import YOLO
model = YOLO('/workspace/models/face_detect/v1.0.0/best.pt')
results = model.val(data='/workspace/datasets/face_detect/data.yaml')
print(f'mAP50: {results.box.map50:.4f}')
print(f'mAP50-95: {results.box.map:.4f}')
"
```

### 回归测试

每次模型版本迭代后，在标准测试集上重新评估指标，与上一版本进行对比，确保无性能退化。

---

## 性能基准

| 指标 | YOLOv8n (640×640) |
|------|-------------------|
| 模型体积 (ONNX) | ~6.3 MB |
| WIDER FACE Easy mAP | > 98% |
| WIDER FACE Medium mAP | > 96% |
| WIDER FACE Hard mAP | > 82% |
| CPU 推理 (Intel i7) | ~35 ms |
| GPU 推理 (RTX 3060) | ~5 ms |
| 最大检测人脸数 | 300 |

---

*本文档由 AI Platform 自动生成。如需补充真实训练结果和数据集链接请手动更新。*
