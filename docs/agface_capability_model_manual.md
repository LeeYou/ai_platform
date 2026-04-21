# agface AI 能力名称与模型配置手册

**北京爱知之星科技股份有限公司 (Agile Star)**
**版本:** v1.0 | **日期:** 2026-04-21 | **文档编号:** AGFACE-CFG-001
**官网：[agilestar.cn](https://agilestar.cn)**

---

## 目录

1. [文档目的](#1-文档目的)
2. [适用范围](#2-适用范围)
3. [agface 能力总览](#3-agface-能力总览)
4. [统一目录与挂载约定](#4-统一目录与挂载约定)
5. [各能力名称与模型配置明细](#5-各能力名称与模型配置明细)
6. [迁移脚本使用说明](#6-迁移脚本使用说明)
7. [生产部署配置步骤](#7-生产部署配置步骤)
8. [能力与模型配置示例](#8-能力与模型配置示例)
9. [非独立能力说明](#9-非独立能力说明)
10. [常见错误与排查](#10-常见错误与排查)
11. [附录：完整能力-模型对照速查表](#11-附录完整能力-模型对照速查表)

---

## 1. 文档目的

本文档用于统一说明 **ai_platform 中 agface 系列 NCNN 能力插件** 的以下配置事项：

- **AI 能力名称** 应如何填写
- **模型文件** 应放在什么目录
- **模型目录结构** 必须满足什么要求
- **宿主机路径** 与 **容器内路径** 如何对应
- **哪些 agface 接口是独立 capability**，哪些不是
- **如何从旧 ai_agface 工程迁移模型** 到 ai_platform 标准目录

本文档面向以下角色：

- **部署同学**
- **运维同学**
- **配置同学**
- **对接 JNI / HTTP / Runtime 的集成开发同学**

---

## 2. 适用范围

本文档覆盖当前已落地并可构建的全部 `agface_*` 独立 C++ capability：

- `agface_face_detect`
- `agface_face_feature_residual256`
- `agface_face_feature_glint512`
- `agface_face_feature_mobilenet256`
- `agface_barehead`
- `agface_fake_photo`
- `agface_face_property`

这些能力统一具备以下特征：

- 基于 `Ai*` C ABI 导出
- 由 `libai_runtime.so` 动态加载
- `AiCreate(model_dir, config_json)` 传入模型目录
- 模型目录中必须存在 `manifest.json`
- 后端统一为 **NCNN**

---

## 3. agface 能力总览

### 3.1 独立 capability 一览

| 能力名称 | 任务类型 | 后端 | 是否独立模型包 | 备注 |
|---|---|---|---|---|
| `agface_face_detect` | 人脸检测 | NCNN | 是 | RetinaFace / SSD 输出 |
| `agface_face_feature_residual256` | 人脸特征提取 | NCNN | 是 | 256 维特征 |
| `agface_face_feature_glint512` | 人脸特征提取 | NCNN | 是 | 512 维特征 |
| `agface_face_feature_mobilenet256` | 人脸特征提取 | NCNN | 是 | 256 维特征，输出 blob 不同 |
| `agface_barehead` | 裸头检测 | NCNN | 是 | 依赖 detection + det3 + modelht |
| `agface_fake_photo` | 翻拍照检测 | NCNN | 是 | 依赖 detection + det3 + model_1/2/3 + yolov7 |
| `agface_face_property` | 人脸属性检测 | NCNN | 是 | 聚合 angle / glasses / mask / hat / fake 等 |

### 3.2 构建开关总览

如需在 CMake 中启用这些能力，使用以下选项：

| CMake 开关 | 对应能力 |
|---|---|
| `BUILD_CAP_AGFACE_FACE_DETECT` | `agface_face_detect` |
| `BUILD_CAP_AGFACE_FACE_FEATURE_RESIDUAL256` | `agface_face_feature_residual256` |
| `BUILD_CAP_AGFACE_FACE_FEATURE_GLINT512` | `agface_face_feature_glint512` |
| `BUILD_CAP_AGFACE_FACE_FEATURE_MOBILENET256` | `agface_face_feature_mobilenet256` |
| `BUILD_CAP_AGFACE_BAREHEAD` | `agface_barehead` |
| `BUILD_CAP_AGFACE_FAKE_PHOTO` | `agface_fake_photo` |
| `BUILD_CAP_AGFACE_FACE_PROPERTY` | `agface_face_property` |
| `BUILD_ALL_AGFACE_CAPS` | 启用全部 agface 能力 |

> **注意：** `agface_*` 能力不会自动纳入 `BUILD_ALL_CAPS`，需要显式开启。

---

## 4. 统一目录与挂载约定

### 4.1 宿主机模型根目录

推荐统一放置在宿主机：

```text
/data/ai_platform/models/
```

每个 capability 独立一个目录：

```text
/data/ai_platform/models/<capability>/<version>/
/data/ai_platform/models/<capability>/current -> <version>
```

例如：

```text
/data/ai_platform/models/agface_face_detect/1.0.0/
/data/ai_platform/models/agface_face_detect/current -> 1.0.0
```

### 4.2 生产容器内模型目录

在生产环境中，宿主机目录会挂载为：

```text
/mnt/ai_platform/models/
```

因此运行时实际查找路径为：

```text
/mnt/ai_platform/models/<capability>/current/
```

Runtime 的资源解析逻辑要求：

- 目录存在
- 目录中存在 `manifest.json`

### 4.3 `current` 约定

平台优先读取：

```text
<models_root>/<capability>/current/
```

因此建议每个 capability 目录都提供：

- 版本目录，例如 `1.0.0`
- 一个 `current` 软链或等价目录

推荐形式：

```bash
cd /data/ai_platform/models/agface_face_detect
ln -sfn 1.0.0 current
```

### 4.4 `AiCreate(model_dir, ...)` 的含义

`AiCreate()` 接收的 `model_dir` 必须是 **能力模型包根目录**，而不是模型根目录的上一级。

正确示例：

```text
/data/ai_platform/models/agface_face_detect/current
```

错误示例：

```text
/data/ai_platform/models/agface_face_detect
/data/ai_platform/models
```

---

## 5. 各能力名称与模型配置明细

## 5.1 `agface_face_detect`

### 能力名称

```text
agface_face_detect
```

### 功能说明

- 人脸检测
- 输出多人脸框与置信度
- 迁移自旧 `ai_agface` 的 RetinaFace / SSD 检测链路

### 推荐模型目录

```text
/data/ai_platform/models/agface_face_detect/current/
```

### 模型目录结构

```text
agface_face_detect/
└─ current/
   ├─ manifest.json
   ├─ detection.param
   └─ detection.bin
```

### 必需文件

- `manifest.json`
- `detection.param`
- `detection.bin`

### 目录特点

- **模型文件直接位于模型根目录**
- **没有 `detection/` 子目录**

### manifest 关键要求

- `name` 建议填写 `agface_face_detect`
- `param_file` 必须是 `detection.param`
- `bin_file` 必须是 `detection.bin`
- `backend` 应为 `ncnn`

---

## 5.2 `agface_face_feature_residual256`

### 能力名称

```text
agface_face_feature_residual256
```

### 功能说明

- 人脸特征提取
- 输出 256 维特征向量

### 推荐模型目录

```text
/data/ai_platform/models/agface_face_feature_residual256/current/
```

### 模型目录结构

```text
agface_face_feature_residual256/
└─ current/
   ├─ manifest.json
   ├─ model.param
   └─ model.bin
```

### 必需文件

- `manifest.json`
- `model.param`
- `model.bin`

### manifest 关键要求

- `name` 建议填写 `agface_face_feature_residual256`
- `param_file` 必须是 `model.param`
- `bin_file` 必须是 `model.bin`
- `feature_dim` 应为 `256`
- `output.format` 应为 `embedding`

---

## 5.3 `agface_face_feature_glint512`

### 能力名称

```text
agface_face_feature_glint512
```

### 功能说明

- 人脸特征提取
- 输出 512 维特征向量
- 当前为 agface 比对链路中的主力 feature 能力之一

### 推荐模型目录

```text
/data/ai_platform/models/agface_face_feature_glint512/current/
```

### 模型目录结构

```text
agface_face_feature_glint512/
└─ current/
   ├─ manifest.json
   ├─ model.param
   └─ model.bin
```

### 必需文件

- `manifest.json`
- `model.param`
- `model.bin`

### 迁移前旧模型来源

旧 ai_agface 中通常来源于：

```text
<old_ai_agface_root>/delivery_package/models/glint360k_r34/glint360k_r34.opt.param
<old_ai_agface_root>/delivery_package/models/glint360k_r34/glint360k_r34.opt.bin
```

迁移后统一改名为：

- `model.param`
- `model.bin`

### manifest 关键要求

- `name` 建议填写 `agface_face_feature_glint512`
- `param_file` 必须是 `model.param`
- `bin_file` 必须是 `model.bin`
- `feature_dim` 应为 `512`
- `output.format` 应为 `embedding`

---

## 5.4 `agface_face_feature_mobilenet256`

### 能力名称

```text
agface_face_feature_mobilenet256
```

### 功能说明

- 人脸特征提取
- 输出 256 维特征向量
- 模型来源为 MobileFaceNet 256 维版本

### 推荐模型目录

```text
/data/ai_platform/models/agface_face_feature_mobilenet256/current/
```

### 模型目录结构

```text
agface_face_feature_mobilenet256/
└─ current/
   ├─ manifest.json
   ├─ model.param
   └─ model.bin
```

### 必需文件

- `manifest.json`
- `model.param`
- `model.bin`

### manifest 关键要求

- `name` 建议填写 `agface_face_feature_mobilenet256`
- `param_file` 必须是 `model.param`
- `bin_file` 必须是 `model.bin`
- `feature_dim` 应为 `256`
- `output.blob` 与 residual / glint 不同，应按迁移脚本生成内容为准

---

## 5.5 `agface_barehead`

### 能力名称

```text
agface_barehead
```

### 功能说明

- 裸头检测
- 先做人脸定位，再结合 `modelht` 做头部判断

### 推荐模型目录

```text
/data/ai_platform/models/agface_barehead/current/
```

### 模型目录结构

```text
agface_barehead/
└─ current/
   ├─ manifest.json
   └─ detection/
      ├─ detection.param
      ├─ detection.bin
      ├─ det3.param
      ├─ det3.bin
      ├─ modelht.param
      └─ modelht.bin
```

### 必需文件

- `manifest.json`
- `detection/detection.param`
- `detection/detection.bin`
- `detection/det3.param`
- `detection/det3.bin`
- `detection/modelht.param`
- `detection/modelht.bin`

### 目录特点

- **模型根目录下必须有 `detection/` 子目录**
- `AiCreate()` 会校验上述文件是否存在

---

## 5.6 `agface_fake_photo`

### 能力名称

```text
agface_fake_photo
```

### 功能说明

- 翻拍照检测
- 组合 live 模型与属性检测模型进行判断

### 推荐模型目录

```text
/data/ai_platform/models/agface_fake_photo/current/
```

### 模型目录结构

```text
agface_fake_photo/
└─ current/
   ├─ manifest.json
   └─ detection/
      ├─ detection.param
      ├─ detection.bin
      ├─ det3.param
      ├─ det3.bin
      ├─ model_1.param
      ├─ model_1.bin
      ├─ model_2.param
      ├─ model_2.bin
      ├─ model_3.param
      ├─ model_3.bin
      ├─ yolov7s320face.param
      └─ yolov7s320face.bin
```

### 必需文件

- `manifest.json`
- `detection/detection.param`
- `detection/detection.bin`
- `detection/det3.param`
- `detection/det3.bin`
- `detection/model_1.param`
- `detection/model_1.bin`
- `detection/model_2.param`
- `detection/model_2.bin`
- `detection/model_3.param`
- `detection/model_3.bin`
- `detection/yolov7s320face.param`
- `detection/yolov7s320face.bin`

---

## 5.7 `agface_face_property`

### 能力名称

```text
agface_face_property
```

### 功能说明

- 人脸属性检测
- 聚合输出：
  - `angle`
  - `glasses`
  - `mask`
  - `facew`
  - `eyeclosed`
  - `hat`
  - `fake`

### 推荐模型目录

```text
/data/ai_platform/models/agface_face_property/current/
```

### 模型目录结构

```text
agface_face_property/
└─ current/
   ├─ manifest.json
   └─ detection/
      ├─ detection.param
      ├─ detection.bin
      ├─ det3.param
      ├─ det3.bin
      ├─ model_1.param
      ├─ model_1.bin
      ├─ model_2.param
      ├─ model_2.bin
      ├─ model_3.param
      ├─ model_3.bin
      ├─ modelht.param
      ├─ modelht.bin
      ├─ yolov7s320face.param
      ├─ yolov7s320face.bin
      ├─ face_landmark_with_attention.param
      └─ face_landmark_with_attention.bin
```

### 必需文件

- `manifest.json`
- `detection/detection.param`
- `detection/detection.bin`
- `detection/det3.param`
- `detection/det3.bin`
- `detection/model_1.param`
- `detection/model_1.bin`
- `detection/model_2.param`
- `detection/model_2.bin`
- `detection/model_3.param`
- `detection/model_3.bin`
- `detection/modelht.param`
- `detection/modelht.bin`
- `detection/yolov7s320face.param`
- `detection/yolov7s320face.bin`
- `detection/face_landmark_with_attention.param`
- `detection/face_landmark_with_attention.bin`

---

## 6. 迁移脚本使用说明

## 6.1 人脸检测模型迁移

脚本：

```text
scripts/migrate_agface_face_detect_model.py
```

示例：

```bash
python scripts/migrate_agface_face_detect_model.py \
  --src "H:/work/训练数据/caffe-base/ai_agface" \
  --dst "/data/ai_platform/models" \
  --version 1.0.0 \
  --overwrite
```

生成目录：

```text
/data/ai_platform/models/agface_face_detect/1.0.0/
```

---

## 6.2 人脸特征模型迁移

脚本：

```text
scripts/migrate_agface_face_feature_models.py
```

支持：

- `residual256`
- `glint512`
- `mobilenet256`
- `all`

示例：

```bash
python scripts/migrate_agface_face_feature_models.py \
  --src "H:/work/训练数据/caffe-base/ai_agface" \
  --dst "/data/ai_platform/models" \
  --version 1.0.0 \
  --which all \
  --overwrite
```

生成目录：

```text
/data/ai_platform/models/agface_face_feature_residual256/1.0.0/
/data/ai_platform/models/agface_face_feature_glint512/1.0.0/
/data/ai_platform/models/agface_face_feature_mobilenet256/1.0.0/
```

---

## 6.3 legacy vision 模型迁移

脚本：

```text
scripts/migrate_agface_vision_models.py
```

支持：

- `barehead`
- `fake_photo`
- `face_property`
- `all`

示例：

```bash
python scripts/migrate_agface_vision_models.py \
  --src "H:/work/训练数据/caffe-base/ai_agface" \
  --dst "/data/ai_platform/models" \
  --version 1.0.0 \
  --which all \
  --overwrite
```

生成目录：

```text
/data/ai_platform/models/agface_barehead/1.0.0/
/data/ai_platform/models/agface_fake_photo/1.0.0/
/data/ai_platform/models/agface_face_property/1.0.0/
```

---

## 7. 生产部署配置步骤

## 7.1 准备宿主机目录

```bash
mkdir -p /data/ai_platform/models
mkdir -p /data/ai_platform/libs
```

## 7.2 迁移或复制模型文件

将对应 capability 的模型包放入：

```text
/data/ai_platform/models/<capability>/<version>/
```

确保目录中包含：

- `manifest.json`
- capability 所要求的全部 `.param/.bin`

## 7.3 创建 `current`

示例：

```bash
cd /data/ai_platform/models/agface_face_feature_glint512
ln -sfn 1.0.0 current
```

## 7.4 校验目录是否正确

示例：

```bash
ls -R /data/ai_platform/models/agface_face_property/current
```

应能看到：

- `manifest.json`
- `detection/`
- 所需全部模型文件

## 7.5 启动或 reload 生产服务

生产环境挂载约定：

```yaml
- /data/ai_platform/models:/mnt/ai_platform/models:ro
```

因此配置完成后，运行时会读取：

```text
/mnt/ai_platform/models/<capability>/current/
```

完成模型就绪后，可通过管理接口触发 reload，再检查 capability 状态。

---

## 8. 能力与模型配置示例

## 8.1 示例：配置 `agface_face_detect`

### 宿主机目录

```text
/data/ai_platform/models/agface_face_detect/1.0.0/
├─ manifest.json
├─ detection.param
└─ detection.bin
```

### 生效目录

```text
/data/ai_platform/models/agface_face_detect/current -> 1.0.0
```

### 对应能力名称

```text
agface_face_detect
```

---

## 8.2 示例：配置 `agface_face_feature_glint512`

### 宿主机目录

```text
/data/ai_platform/models/agface_face_feature_glint512/1.0.0/
├─ manifest.json
├─ model.param
└─ model.bin
```

### 生效目录

```text
/data/ai_platform/models/agface_face_feature_glint512/current -> 1.0.0
```

### 对应能力名称

```text
agface_face_feature_glint512
```

---

## 8.3 示例：配置 `agface_fake_photo`

### 宿主机目录

```text
/data/ai_platform/models/agface_fake_photo/1.0.0/
├─ manifest.json
└─ detection/
   ├─ detection.param
   ├─ detection.bin
   ├─ det3.param
   ├─ det3.bin
   ├─ model_1.param
   ├─ model_1.bin
   ├─ model_2.param
   ├─ model_2.bin
   ├─ model_3.param
   ├─ model_3.bin
   ├─ yolov7s320face.param
   └─ yolov7s320face.bin
```

### 生效目录

```text
/data/ai_platform/models/agface_fake_photo/current -> 1.0.0
```

### 对应能力名称

```text
agface_fake_photo
```

---

## 9. 非独立能力说明

以下内容 **不是当前独立导出的 capability**，因此不需要单独配置 capability 模型包：

### 9.1 `agface_face_align`

当前不作为独立 capability 暴露。

- 对齐逻辑已经内化到 feature 插件内部
- 调用方不需要为其单独准备模型目录

### 9.2 `agface_face_compare`

当前不作为独立 C++ capability 暴露。

平台当前提供的是 Python 组合接口：

```text
POST /api/v1/agface/face_compare
```

它会组合调用：

- `agface_face_detect` 或跳过检测
- `agface_face_feature_<variant>`

因此：

- **不需要准备 `agface_face_compare` 模型目录**
- 但需要确保 detector / feature 对应模型已配置好

### 9.3 `FaceDetector` helper

`_agface_common` 中的 `FaceDetector` 仅为：

- `agface_barehead`
- `agface_fake_photo`
- `agface_face_property`

这些插件的内部公共组件，**不是外部 capability**。

---

## 10. 常见错误与排查

## Q1: 配了模型目录但能力加载失败，为什么？

常见原因：

- 目录里缺少 `manifest.json`
- `current` 指向错了目录
- 把 `model_dir` 传成了 capability 根目录，而不是具体版本目录或 `current`
- 某些 `.param/.bin` 文件缺失

---

## Q2: `agface_barehead` / `agface_fake_photo` / `agface_face_property` 为什么不能像 face_detect 一样把文件直接放根目录？

因为这三类插件的代码会显式校验：

```text
<model_dir>/detection/...
```

因此必须保留 `detection/` 子目录结构。

---

## Q3: `agface_face_feature_glint512` 原始文件名不是 `model.param`，为什么部署时要改名？

因为迁移脚本会统一输出标准模型包格式：

- `model.param`
- `model.bin`
- `manifest.json`

feature 插件也是通过 `manifest.json` 中的 `param_file` / `bin_file` 去加载，不再依赖旧工程原始文件名。

---

## Q4: `agface_face_compare` 需要单独模型吗？

**不需要。**

它是 Python 编排层接口，不是独立 capability。实际依赖：

- 一个 detector capability
- 一个 feature capability

---

## Q5: 如何快速判断一个 agface 能力是否配置正确？

检查三件事：

- 能力名称是否与目录一致
- `current/manifest.json` 是否存在
- 模型文件名和目录层级是否与本文档一致

---

## 11. 附录：完整能力-模型对照速查表

| 能力名称 | 是否独立 capability | 模型目录结构 | 关键文件 |
|---|---|---|---|
| `agface_face_detect` | 是 | 根目录平铺 | `manifest.json`, `detection.param`, `detection.bin` |
| `agface_face_feature_residual256` | 是 | 根目录平铺 | `manifest.json`, `model.param`, `model.bin` |
| `agface_face_feature_glint512` | 是 | 根目录平铺 | `manifest.json`, `model.param`, `model.bin` |
| `agface_face_feature_mobilenet256` | 是 | 根目录平铺 | `manifest.json`, `model.param`, `model.bin` |
| `agface_barehead` | 是 | `detection/` 子目录 | `manifest.json`, `detection/detection.*`, `detection/det3.*`, `detection/modelht.*` |
| `agface_fake_photo` | 是 | `detection/` 子目录 | `manifest.json`, `detection/detection.*`, `detection/det3.*`, `detection/model_1/2/3.*`, `detection/yolov7s320face.*` |
| `agface_face_property` | 是 | `detection/` 子目录 | `manifest.json`, `detection/detection.*`, `detection/det3.*`, `detection/model_1/2/3.*`, `detection/modelht.*`, `detection/yolov7s320face.*`, `detection/face_landmark_with_attention.*` |
| `agface_face_align` | 否 | 无需单独配置 | 内部复用 |
| `agface_face_compare` | 否 | 无需单独配置 | 组合接口 |

---

> 📌 **维护说明：** 当新增新的 `agface_*` capability，或调整 manifest / 模型目录结构时，必须同步更新本文档。
>
> | 版本 | 日期 | 修改内容 | 作者 |
> |---|---|---|---|
> | v1.0 | 2026-04-21 | 初始版本，覆盖全部已落地 agface capability 的 AI 名称与模型配置要求 | AI 平台团队 |
