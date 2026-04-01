# desktop_recapture_detect

桌面翻拍检测 — 判断摄像头画面是**真实肖像**还是**桌面照片浏览器翻拍**（虚拟摄像头作弊检测）。

## 模型架构

EfficientNet-B0 二分类：

| 类别 | 标签 |
|------|------|
| real | 0 |
| fake | 1 |

输入尺寸：224×224，ImageNet 归一化。

## 训练数据准备

数据集目录结构：

```
/workspace/datasets/desktop_recapture_detect/
├── real/                    # 真实肖像照片
├── fake/                    # 由 generate_fake.py 自动生成
├── desktop_screen/          # 桌面截图模板
├── pic_viewer/              # 空白查看器模板（RGB 245,245,245）
├── pic_viewer_temp2/        # 打开真实图片的查看器模板
└── desktop_screen_temp/     # 手动截取的翻拍截图
```

### 生成假样本

```bash
python generate_fake.py --dataset /workspace/datasets/desktop_recapture_detect/ \
                        --config config.json

# 预览模式（写入 /tmp）
python generate_fake.py --dataset /workspace/datasets/desktop_recapture_detect/ --preview

# 清除旧输出后重新生成
python generate_fake.py --dataset /workspace/datasets/desktop_recapture_detect/ --clear-output
```

生成器混合以下模板来源：
- `desktop_screen/` 桌面截图
- `pic_viewer/` 空白查看器模板
- `pic_viewer_temp2/` 打开图片的查看器模板
- `desktop_screen_temp/` 手动翻拍截图（直接拷贝到 fake 集）

## 训练

```bash
python train.py --config config.json \
                --dataset /workspace/datasets/desktop_recapture_detect/ \
                --output /workspace/models/desktop_recapture_detect/v1.0.0/ \
                --version 1.0.0
```

两阶段训练：

| 阶段 | 轮数 | 说明 |
|------|------|------|
| Phase 1 | 5 | 冻结 backbone，仅训练分类头 |
| Phase 2 | 25 | 全参数微调，CosineAnnealingLR，早停 patience=10 |

## 评估

```bash
python evaluate.py --config config.json \
                   --dataset /workspace/datasets/desktop_recapture_detect/ \
                   --checkpoint /workspace/models/desktop_recapture_detect/v1.0.0/best.pth
```

## ONNX 导出

```bash
python export.py --output /workspace/models/desktop_recapture_detect/v1.0.0/ \
                 --version 1.0.0
```

导出文件：
- `model.onnx` — ONNX 模型
- `preprocess.json` — 预处理配置
- `labels.json` — 类别标签
- `manifest.json` — 模型元数据

## 来源

迁移自 [LeeYou/recapture_detect](https://github.com/LeeYou/recapture_detect)（dev 分支）。
