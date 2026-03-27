# 图像修复（`image_inpaint`）

## 技术选型

| 项目 | 说明 |
|------|------|
| 模型架构 | LaMa/DeepFill |
| 深度学习框架 | PyTorch 2.x / PaddlePaddle 2.x |
| 主要依赖 | 详见 `requirements.txt` |

LaMa / DeepFill 利用傅里叶卷积或门控卷积填充遮挡区域，保证结构与纹理一致性。

---

## 推荐开源数据集

- **Places2 (LaMa训练集)**
- **CelebA-HQ**
- **Paris StreetView**

> **注意**：训练前请确认数据集许可证，并遵循相应使用条款。

---

## 训练方法

### 1. 环境准备

```bash
pip install -r requirements.txt
```

### 2. 准备数据集

将数据集放置于 `/workspace/datasets/image_inpaint/` 目录，并按以下结构组织：

```
/workspace/datasets/image_inpaint/
├── train/
├── val/
└── test/
```

### 3. 启动训练

```bash
python train.py \
    --config config.json \
    --dataset /workspace/datasets/image_inpaint/ \
    --output /workspace/models/image_inpaint/v1.0.0/ \
    --version 1.0.0
```

主要超参数（见 `config.json`）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `batch_size` | 8 | 批大小，可根据显存调整 |
| `epochs` | 100 | 最大训练轮次 |
| `lr0` | 0.01 | 初始学习率 |
| `lrf` | 0.001 | 最终学习率（余弦衰减倍率） |
| `patience` | 20 | 早停等待轮次 |
| `val_split` | 0.1 | 验证集比例（无独立 val 目录时） |
| `amp` | True | 是否启用混合精度训练 |

### 4. 导出模型

```bash
python export.py \
    --weights /workspace/models/image_inpaint/v1.0.0/best.pt \
    --format onnx
```

---

## 测试方法

### 功能测试

报告 LPIPS / FID / PSNR；人工评估修复边缘自然度；测试大面积遮挡（>50%）场景。

### 推理示例

```bash
# 以推理脚本为例（需根据实际部署脚本调整）
python infer.py \
    --weights /workspace/models/image_inpaint/v1.0.0/best.pt \
    --input /path/to/test/data \
    --output /path/to/results/
```

### 回归测试

每次模型版本迭代后，在标准测试集上重新评估指标，与上一版本进行对比，确保无性能退化。

---

*本文档由 AI Platform 自动生成，如需补充真实训练结果和数据集链接请手动更新。*
