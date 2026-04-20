# ai_agface → ai_platform 迁移设计

> 将旧企业级人证比对 SDK **ai_agface**（NCNN + OpenCV）逐步合并进 **ai_platform**
> 的能力插件体系。所有新能力统一加前缀 `agface_`，以区别现有 ONNX 系列能力。

## 0. 现状

- 旧库 `ai_agface`：C++17 + NCNN + OpenCV + OpenSSL，多 DLL 拼装的人脸比对管线
  （detect → align → feature → compare），并带 Pipeline 引擎与 RSA License 校验。
- 新库 `ai_platform/cpp/`：C++17 + ONNXRuntime + 统一 `Ai*` C ABI，每个能力一个
  `lib<name>.so`，由 `libai_runtime.so` 统一加载、调度、License 校验。Pipeline 在
  Python `@/prod/web_service/pipeline_engine.py` 层。

## 1. 映射关系总览

| 旧（`ai_agface`） | 新（`ai_platform`） | 迁移动作 |
|---|---|---|
| `include/ai_module/*.h`（每能力一组 C API） | `@/cpp/sdk/ai_capability.h` 统一 ABI | **重写** 为 `Ai*` ABI |
| `src/ai_modules/face_detect/face_detect_retina.*` | `cpp/capabilities/agface_face_detect/` | **移植**，改后端 ABI |
| `src/ai_modules/face_align/face_align.*` | `cpp/capabilities/agface_face_align/`（后续轮） | 待迁 |
| `src/ai_modules/face_feature/*` | `cpp/capabilities/agface_face_feature_*`（后续轮） | 待迁 |
| `src/ai_modules/face_compare/face_compare.*` | `cpp/capabilities/agface_face_compare/`（后续轮） | 待迁 |
| `src/ai_modules/common/ncnn_session.h` | `cpp/capabilities/_agface_common/include/agface/ncnn_session.h` | **移植**（精简） |
| `src/infra/instance_pool.h` | `cpp/capabilities/_agface_common/include/agface/instance_pool.h` | **移植**（去 License 耦合） |
| `src/infra/license_*.{h,cpp}` + `rsa_verify.*` | 丢弃；License 改由 `libai_runtime.so` 统一 | **不迁** |
| `src/infra/path_resolver.*` | 丢弃；改用挂载目录约定 | **不迁** |
| `src/infra/pipeline*.{h,cpp}` + `pipeline_builder.h` + `pipeline_context.h` | 丢弃；改用 `@/prod/web_service/pipeline_engine.py` | **不迁** |
| `src/agface/*` 应用层（service / vision_analyzer / backends） | 丢弃；改由 Python 层编排 | **不迁** |
| `src/jni/agface_jni.cpp` | 保留规划但本轮不做；后续接到 `libai_runtime.so` | **后续** |
| `delivery_package/models/detection/detection.{param,bin}` | `/data/ai_platform/models/agface_face_detect/1.0.0/` + `manifest.json` | **迁移脚本** `@/scripts/migrate_agface_face_detect_model.py` |

## 2. 构建系统改动

1. 新增 `@/cpp/cmake/FindNCNN.cmake`，三级回退（vendored / `ncnnConfig.cmake` /
   `NCNN_ROOT`），统一 `NCNN::NCNN` 导入目标。
2. `@/cpp/cmake/CapabilityPlugin.cmake` 新增关键字 `BACKEND ONNX|NCNN|NONE`
   与 `EXTRA_LIBS`：
   - `NCNN` 后端自动 `include(FindNCNN)` 并 `find_package(OpenCV)`，
     定义 `AI_BACKEND_NCNN=1`。
   - 默认 `ONNX`，与历史能力向后兼容。
3. `@/cpp/CMakeLists.txt` 新增选项：
   - `BUILD_ALL_AGFACE_CAPS`、`BUILD_CAP_AGFACE_FACE_DETECT`。
   - **不纳入 `BUILD_ALL_CAPS`**：必须显式开启，避免无 NCNN 环境下失败。
4. Docker：
   - `@/build/Dockerfile.linux_x86` 安装 `libncnn-dev libopencv-dev libomp-dev`。
   - `@/prod/Dockerfile` 安装 `libncnn1 libopencv-core4.5d libopencv-imgproc4.5d libopencv-imgcodecs4.5d libgomp1`。

## 3. 共享适配层 `_agface_common`

内部静态库（`agface_common`），供所有 agface_* 插件 PRIVATE 链接。不导出符号、
不安装。目录：`@/cpp/capabilities/_agface_common/`。

- `include/agface/instance_pool.h` — RAII 借出对象池。
- `include/agface/ncnn_session.h` — 共享 `ncnn::Net` + 一次性 `Extractor`。
- `include/agface/manifest.h` / `manifest.cpp` — 解析 `manifest.json`（约定字段：
  `param_file`, `bin_file`, `input.blob/base_size/color/mean/norm`,
  `output.blob/format`, `thresholds.score/min_face/max_image_dim`）。
- `include/agface/image_utils.h` / `image_utils.cpp` — `AiImage → cv::Mat(BGR)`，
  正确处理 `stride` 与 `color_format ∈ {BGR, RGB, GRAY}`。
- `include/agface/json_result.h` / `json_result.cpp` — `fillResult` / `fillError` /
  `freeResult`，严格遵守 SDK "malloc-dup + 插件 AiFreeResult 释放" 约定。

## 4. 首轮能力：`agface_face_detect`

目录：`@/cpp/capabilities/agface_face_detect/`

- `CMakeLists.txt` — `add_capability_plugin(BACKEND NCNN EXTRA_LIBS agface_common)`。
- `agface_face_detect.h` — `AgfaceFaceDetectContext`。
- `agface_face_detect.cpp` — `Ai*` ABI 实现：
  - `AiCreate` → 解析 `manifest.json`。
  - `AiInit` → 加载 ncnn::Net 共享 + 建 InstancePool（size = hw_concurrency/2）。
  - `AiInfer` → AiImage → BGR → `from_pixels_resize` 保持 aspect 到 `base_size²` →
    `substract_mean_normalize` → `extract("detection_out")` → SSD 解码 → NMS 省略
    （SSD 头通常不需再 NMS）→ 按 score/min_face 过滤 → 输出 JSON。
  - `AiReload` → 互斥下 staging 构建 + 原子替换 `pool`/`shared_net`/`manifest`，
    旧 pool 析构时自动等待所有 `ScopedInstance` 归还。
  - `AiGetInfo` → 返回 `{name, version, backend, input, output, thresholds}`。
  - `AiFreeResult` → 转调 `agface::freeResult`。

### 输出 JSON 结构
```json
{
  "faces": [
    {"bbox": [x, y, w, h], "confidence": 0.93, "class_id": 1}
  ],
  "image_size": [W, H]
}
```

## 5. 模型包迁移

运行 `@/scripts/migrate_agface_face_detect_model.py`：

```powershell
python scripts/migrate_agface_face_detect_model.py `
    --src "H:/work/训练数据/caffe-base/ai_agface" `
    --dst "//DATA-SERVER/data/ai_platform/models" `
    --version 1.0.0
```

生成：
```
/data/ai_platform/models/agface_face_detect/1.0.0/
├── detection.param
├── detection.bin
└── manifest.json        # 包含 sha256 校验
```

挂载到 prod 容器：`/mnt/ai_platform/models/agface_face_detect/1.0.0/`。
按平台约定建 `current` 软链：`/mnt/ai_platform/models/agface_face_detect/current → 1.0.0`。

## 6. 验收

### 6.1 非回归（现有 ONNX 插件）
```bash
cmake -S cpp -B build-baseline -DBUILD_ALL_CAPS=ON -DBUILD_CAP_AGFACE_FACE_DETECT=OFF
cmake --build build-baseline -j
# 期望：face_detect / handwriting_reco / recapture_detect / id_card_classify /
#       desktop_recapture_detect 正常编译，不触发 NCNN/OpenCV 查找。
```

### 6.2 首次启用 agface
```bash
cmake -S cpp -B build-agface -DBUILD_ALL_CAPS=OFF -DBUILD_CAP_AGFACE_FACE_DETECT=ON
cmake --build build-agface -j
# 产出：
#   build-agface/lib/libagface_common.a
#   build-agface/lib/libagface_face_detect.so
```

### 6.3 生产端集成验证
1. 把 `libagface_face_detect.so` 拷贝到 `/mnt/ai_platform/libs/agface_face_detect/1.0.0/lib/`。
2. 运行迁移脚本把模型写到 `/mnt/ai_platform/models/agface_face_detect/1.0.0/`。
3. `POST /api/v1/reload`（Admin）→ `GET /api/v1/capabilities`
   应见 `agface_face_detect` 状态 `loaded`。
4. `POST /api/v1/infer/agface_face_detect`（multipart jpg）→ 返回 `{"faces":[...]}`。

## 7. 第二轮（已完成）

### 7.1 新增能力插件

- **`agface_face_feature_residual256`**（BACKEND=NCNN，256 维）。迁移自旧
  `FaceFeatureResidual256` + `FaceFeatureBase::extract`。
- **`agface_face_feature_glint512`**（BACKEND=NCNN，512 维）。迁移自旧
  `FaceFeatureGlint512`。两个插件共享 `@/cpp/capabilities/_agface_common/include/agface/feature_plugin_impl.h`
  的 Ai* ABI 骨架，差异（模型名/维度/输入色彩）**完全由各自的 manifest.json 驱动**。

### 7.2 扩展的 `_agface_common`

- **`face_align.h/.cpp`** — 5 点相似变换对齐到 112×112，闭合解 + 双线性重采样，
  与旧 `face_feature_base.h::alignFace` 算法逐行等价。landmarks=nullptr 时使用
  合成地标（便于客户端直接喂一张已粗裁剪的人脸图）。
- **`feature_extract.h/.cpp`** — 通用特征提取：对齐 → NCNN 预处理 → forward →
  L2 归一化，manifest 驱动差异。
- **`feature_plugin_impl.h`** — 完整 Ai* ABI 模板头，供后续更多 feature 插件
  一行 include 复用。
- **`manifest.h`** 新增 `feature_dim` 字段 + 解析逻辑，供输出维度自检。

### 7.3 特征插件输出 JSON

```json
{
  "feature": [0.0123, -0.0456, ...],
  "dim": 256,
  "l2_normalized": true
}
```
调用方可直接对两个向量做 **点积 = 余弦相似度**，然后套用旧平台的
`calibrateScore` 分段映射（`(-1,0)→[0,10]`, `(0,0.3)→[10,30]`, `(0.3,0.5)→[30,60]`,
`(0.5,0.7)→[60,85]`, `(0.7,1.0)→[85,100]`）得到 0-100 分的比对结果。

### 7.4 新增模型迁移脚本

`@/scripts/migrate_agface_face_feature_models.py`，支持 `--which residual256|glint512|all`：

```bash
python scripts/migrate_agface_face_feature_models.py \
    --src "H:/work/训练数据/caffe-base/ai_agface" \
    --dst "/data/ai_platform/models" \
    --version 1.0.0 \
    --which all
```

生成：
```
/data/ai_platform/models/
  agface_face_feature_residual256/1.0.0/{model.param,model.bin,manifest.json}
  agface_face_feature_glint512/1.0.0/{model.param,model.bin,manifest.json}
```

### 7.5 架构决策（重要）

- **`agface_face_align` 作为独立能力暂不导出**：对齐已内化到 feature 插件中（
  输入整张人脸 crop，内部对齐到 112×112 后提特征），外部无需再调一次 align。
- **`agface_face_compare` 作为独立能力暂不导出**：当前 `Ai*` ABI 只接受
  `AiImage + AiResult`，不适合"两 feature 向量进、一分数出"的纯计算调用；
  客户端收到两份 feature 后自行计算点积 + 分数映射即可。
- 若后续需要"一个 HTTP 调用完成整套比对"，应走 **composite capability** 方案
  或扩展 `Ai*` ABI 增加"通用 JSON 输入"变体，均列入第三轮。

## 8. 第三轮（已完成）

### 8.1 新 feature 能力 `agface_face_feature_mobilenet256`

- `cpp/capabilities/agface_face_feature_mobilenet256/` — MobileFaceNet 256 维，
  output blob = `fc1`（与 residual256/glint512 的 `pre_fc1` 不同）。完全复用
  `feature_plugin_impl.h`，插件 `.cpp` 仍为 14 行（define + include）。
- 模型迁移脚本扩展：`--which all | residual256 | glint512 | mobilenet256`。
- ABI 烟雾测试自动覆盖（同一个 `test_agface_feature_plugins.py`）。

### 8.2 Python 层 composite：`POST /api/v1/agface/face_compare`

替代旧 `agface_compare_jpg` 入口点，无需新 C++ 插件。流程：

```
image_a, image_b (multipart)
    │
    ├── [可选] agface_face_detect 选最大人脸 → 15% margin crop → JPEG 重编码
    │
    ├── agface_face_feature_<variant>.infer(image_a_crop) → feature_a (L2)
    ├── agface_face_feature_<variant>.infer(image_b_crop) → feature_b (L2)
    │
    └── cosine = dot(a, b)                 (两向量已 L2 归一化)
        score  = calibrate_score(cosine)    (与旧 SimilarityCalculator 分段映射一致)
```

实现：
- `prod/web_service/agface_compare.py` —— 纯 Python 帮助模块（零额外依赖），
  提供 `cosine_similarity` / `calibrate_score` / `pick_largest_face_bbox` /
  `crop_image_to_bbox` / `compare_faces` 编排函数。
- `prod/web_service/main.py` 新增 `/api/v1/agface/face_compare` FastAPI 端点 +
  `_encode_image_jpeg` 工具函数。
- Form 字段：
  - `feature_model` ∈ `{residual256, glint512, mobilenet256}`（默认 glint512）
  - `detector` = 能力名 / `"none"` / 空（跳过检测，适用于已 crop 的面部图）
  - `margin_ratio` = 默认 `0.15`
- 返回：

```json
{
  "code": 0,
  "message": "success",
  "total_time_ms": 42.18,
  "feature_capability": "agface_face_feature_glint512",
  "detector_capability": "agface_face_detect",
  "faces": {"image_a": 1, "image_b": 1},
  "cosine": 0.823456,
  "score": 91.17,
  "dim": 512,
  "feature_a_sample": [0.0123, -0.0456, ...],   // 前 8 维
  "feature_b_sample": [0.0138, -0.0441, ...]
}
```

单元测试：`tests/prod/test_agface_compare.py` —— 不依赖 C++ 运行时，覆盖余弦
计算、分段映射 6 个锚点、bbox 最大化、composite 编排（含 detector 开关）。

### 8.3 架构决策回顾

- **不做 C++ composite capability**：composite 逻辑属于编排层（Python），
  放到 C++ 插件会让每次升级都要重新发 SO、也无法复用已有的 runtime 实例池。
- **不扩展 `Ai*` ABI**：当前 ABI 专注于"单图像 → 单 JSON"的纯 GPU 计算单元，
  用 Python 组合既简单又能复用 `_infer_for_pipeline` / 并发闸门 / A/B 测试。
- **`detector=none` 模式**：让已有客户端代码（自己 crop）也能直接接入，
  给 JNI 兼容层一个低耦合的落脚点。

## 9. 第四轮（已完成）

### 9.1 新增三类 legacy vision 能力插件

- **`agface_barehead`** — 迁移旧 `barehead_module`，流程为：`FaceDetector` 取最大脸 →
  `modelht` 三尺度输出 → 头顶区域命中概率聚合；无有效输出时退化到 legacy heuristic。
- **`agface_fake_photo`** — 迁移旧 `fake_photo_module`，流程为：最大脸 → 三个 live 模型
  (`model_1/2/3`) 加权估计真实人脸概率 → `1-real` 得到翻拍概率；再用
  `yolov7s320face` 的 label=6 规则强提升翻拍判定。
- **`agface_face_property`** — 迁移旧 `face_property_module`，聚合输出：
  `angle / glasses / mask / facew / eyeclosed / hat / fake`。其中姿态优先用
  `face_landmark_with_attention` mesh 结果，失败则退回 heuristic。

### 9.2 `_agface_common` 扩展

- **`vision_analysis_common.h/.cpp`** — 抽出旧 `vision_analysis_common` 的 heuristic：
  `preprocessLegacyVisionImage`、`estimateHat/Mask/Glasses/EyeClosed/FakeLegacy`、
  `buildAngleStringLegacy`。
- **`legacy_vision_context.h/.cpp`** — 抽出三类能力共享的 NCNN 资源装配：
  live 模型加载、`yolov7s320face` 属性检测、mesh 姿态、hat 三尺度输出解析。

### 9.3 新增模型迁移脚本与测试

- 新增 `@/scripts/migrate_agface_vision_models.py`，支持
  `barehead | fake_photo | face_property | all`。
- 新增 `tests/prod/test_agface_vision_plugins.py`，覆盖 `agface_barehead` /
  `agface_fake_photo` / `agface_face_property` 的 ABI 烟雾测试。

## 10. 第五轮（候选）

- **JNI 兼容层** `libagface_jni.so`，保持旧 `com.agile.comparison.util.AgFace`
  客户端签名不变，内部通过 HTTP → `/api/v1/agface/face_compare`（或直连
  libai_runtime）落地，客户代码零改动。
- 默认 feature 能力的选型评估（glint512 vs residual256 vs mobilenet256），
  在真实数据集上跑 ROC / AUC 后在 manifest 里固化推荐版本。
