# 测试子系统设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-27**

---

## 1. 概述

测试子系统提供模型推理测试能力，支持单样本可视化测试、批量精度评估和多版本结果对比，所有操作通过 Web 界面完成。测试阶段使用 Python + ONNXRuntime 作为推理后端，快速验证模型效果，无需依赖 C++ SO 编译。

---

## 2. 容器设计

| 属性 | 值 |
|------|-----|
| 镜像名 | `agilestar/ai-test:latest` |
| 基础镜像 | `python:3.11-slim`（可选含 CUDA 版本） |
| 服务端口 | 8002（Web 管理界面） |
| 后端框架 | Python FastAPI |
| 前端框架 | Vue3 + Element Plus |
| 推理后端 | ONNXRuntime（CPU/GPU 自动选择） |

### 挂载目录

| 宿主机路径 | 容器路径 | 模式 |
|-----------|---------|------|
| `/data/ai_platform/models/` | `/workspace/models` | 只读 |
| `/data/ai_platform/datasets/` | `/workspace/datasets` | 只读 |
| `/data/ai_platform/logs/test/` | `/workspace/logs` | 读写 |

---

## 3. Web 测试页面功能

### 3.1 页面结构

```
测试管理 Web
├── 能力选择（一级页面）
│   ├── 已加载模型的 AI 能力卡片列表
│   ├── 显示能力名称、当前模型版本、最后测试时间
│   └── 点击进入对应能力的测试页面
└── 能力测试（二级页面）
    ├── 单样本测试
    │   ├── 上传图片 / 文件
    │   ├── 从数据集目录选取样本
    │   └── 可视化推理结果
    ├── 批量测试
    │   ├── 指定数据集路径
    │   ├── 批量推理执行（进度条）
    │   └── 精度报告（Precision / Recall / F1 / mAP）
    └── 版本对比
        ├── 选择两个模型版本
        ├── 对同一组样本同时推理
        └── 并排展示结果差异
```

### 3.2 功能模块详述

#### 能力选择（一级页面）

- 扫描 `/workspace/models/` 目录，自动识别已有模型包
- 读取各能力 `manifest.json` 展示能力信息
- 展示：能力名称（中文）、版本号、后端类型、最后修改时间
- 支持搜索/筛选能力

#### 单样本测试

- 支持拖拽上传图片（JPG/PNG/BMP）
- 支持从数据集目录树浏览并选取样本
- 调用后端推理 API，返回结构化结果
- 可视化展示：
  - **目标检测类**：在图片上叠加检测框、类别标签、置信度
  - **分类类**：展示 Top-K 分类结果及置信度条形图
  - **OCR 类**：展示识别文字及位置框
  - 显示推理耗时（毫秒）

#### 批量测试

- 用户指定数据集子目录（如 `/workspace/datasets/face_detect/test/`）
- 后端异步批量推理，WebSocket 推送进度
- 完成后输出精度报告：
  - Precision、Recall、F1-Score（分类/检测）
  - mAP@0.5、mAP@0.5:0.95（检测任务）
  - 混淆矩阵（分类任务）
- 支持导出报告为 CSV/PDF

#### 版本对比

- 同时加载同一能力的两个模型版本（如 v1.0.0 vs v1.1.0）
- 选取一组测试样本，两版本并行推理
- 并排展示结果，高亮差异之处
- 输出对比精度统计表

---

## 4. 推理后端设计

测试阶段使用 Python ONNXRuntime 实现推理，不依赖 C++ SO，便于快速迭代。

### 推理模块接口约定

```python
class CapabilityInferencer:
    """每个 AI 能力对应一个推理器实现"""

    def __init__(self, model_dir: str):
        """
        初始化，加载模型包
        model_dir: 模型包目录，含 manifest.json 和 model.onnx
        """

    def infer(self, image: np.ndarray) -> dict:
        """
        单次推理
        image: HWC BGR uint8 numpy array
        返回: 统一结果字典，格式由 manifest 中 capability 类型决定
        """

    def batch_infer(self, images: List[np.ndarray]) -> List[dict]:
        """批量推理"""
```

### 统一结果格式

#### 目标检测结果

```json
{
  "capability": "face_detect",
  "model_version": "1.0.0",
  "inference_time_ms": 12.5,
  "detections": [
    {
      "label": "face",
      "confidence": 0.95,
      "bbox": { "x1": 100, "y1": 80, "x2": 300, "y2": 320 }
    }
  ]
}
```

#### 分类结果

```json
{
  "capability": "id_card_classify",
  "model_version": "1.0.0",
  "inference_time_ms": 5.2,
  "classifications": [
    { "label": "id_front", "confidence": 0.98 },
    { "label": "id_back", "confidence": 0.01 }
  ]
}
```

---

## 5. 测试脚本规范

每个 AI 能力在 `test/` 目录下可提供对应的推理器实现：

```
test/
├── backend/
│   ├── main.py                    # FastAPI 主程序
│   ├── inferencers/
│   │   ├── base.py                # 推理器基类
│   │   ├── face_detect.py         # 人脸检测推理器
│   │   ├── handwriting_reco.py    # 手写签字推理器
│   │   └── <capability>.py
│   └── evaluators/
│       ├── detection_evaluator.py # 检测精度评估
│       └── classification_evaluator.py
└── frontend/
    └── src/
```

如果能力没有专用推理器，系统使用通用 ONNXRuntime 推理器，依据 `manifest.json` 中的配置自动进行预处理和后处理。

---

## 6. 精度评估指标

| 任务类型 | 评估指标 |
|---------|---------|
| 目标检测 | mAP@0.5、mAP@0.5:0.95、Precision、Recall |
| 二分类 | Accuracy、Precision、Recall、F1、AUC-ROC |
| 多分类 | Accuracy、Per-Class Precision/Recall、混淆矩阵 |
| OCR | 字符准确率（CER）、行准确率 |

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
