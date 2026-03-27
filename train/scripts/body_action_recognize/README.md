# 肢体动作识别（`body_action_recognize`）

## 技术选型

| 项目 | 说明 |
|------|------|
| 模型架构 | ST-GCN/PoseC3D |
| 深度学习框架 | PyTorch 2.x / PaddlePaddle 2.x |
| 主要依赖 | 详见 `requirements.txt` |

从姿态骨架序列（关键点时序图）出发，使用 ST-GCN 或 PoseC3D 建模时空依赖。

---

## 推荐开源数据集

- **NTU RGB+D 120**
- **Penn Action**
- **COCO WholeBody**
- **Kinetics-Skeleton**

> **注意**：训练前请确认数据集许可证，并遵循相应使用条款。

---

## 训练方法

### 1. 环境准备

```bash
pip install -r requirements.txt
```

### 2. 准备数据集

将数据集放置于 `/workspace/datasets/body_action_recognize/` 目录，并按以下结构组织：

```
/workspace/datasets/body_action_recognize/
├── train/
├── val/
└── test/
```

### 3. 启动训练

```bash
python train.py \
    --config config.json \
    --dataset /workspace/datasets/body_action_recognize/ \
    --output /workspace/models/body_action_recognize/v1.0.0/ \
    --version 1.0.0
```

主要超参数（见 `config.json`）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `batch_size` | 16 | 批大小，可根据显存调整 |
| `epochs` | 80 | 最大训练轮次 |
| `lr0` | 0.01 | 初始学习率 |
| `lrf` | 0.001 | 最终学习率（余弦衰减倍率） |
| `patience` | 20 | 早停等待轮次 |
| `val_split` | 0.1 | 验证集比例（无独立 val 目录时） |
| `amp` | True | 是否启用混合精度训练 |

### 4. 导出模型

```bash
python export.py \
    --weights /workspace/models/body_action_recognize/v1.0.0/best.pt \
    --format onnx
```

---

## 测试方法

### 功能测试

在 NTU RGB+D Cross-Subject 协议下报告 Top-1 准确率；可视化激活骨架节点。

### 推理示例

```bash
# 以推理脚本为例（需根据实际部署脚本调整）
python infer.py \
    --weights /workspace/models/body_action_recognize/v1.0.0/best.pt \
    --input /path/to/test/data \
    --output /path/to/results/
```

### 回归测试

每次模型版本迭代后，在标准测试集上重新评估指标，与上一版本进行对比，确保无性能退化。

---

*本文档由 AI Platform 自动生成，如需补充真实训练结果和数据集链接请手动更新。*
