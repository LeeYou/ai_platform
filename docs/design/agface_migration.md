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

## 7. 下一步（第二轮）

- `agface_face_align`（BACKEND=NONE，纯仿射）
- `agface_face_feature_residual256`、`agface_face_feature_glint512`（BACKEND=NCNN）
- `agface_face_compare`（BACKEND=NONE，余弦相似度）
- 预置 pipeline `agface_face_compare_v1.json`（prod pipeline_engine）
- JNI 兼容层 `libagface_jni.so` —— 保留旧 `com.agile.comparison.util.AgFace` 签名
- 第三轮：`agface_face_property`、`agface_fake_photo`、`agface_barehead`、
  `agface_face_feature_mobilenet256`
