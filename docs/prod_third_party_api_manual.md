# AI Platform 生产接口文档（第三方调用版）

**北京爱知之星科技股份有限公司 (Agile Star)**  
**版本：** v1.0  
**适用服务：** `prod/web_service` 生产推理服务  
**基础前缀：** `/api/v1`

---

## 1. 文档目的

本文档面向第三方调用者，说明当前 `ai_platform` 生产环境已提供的对外 REST API，用于：

- 查询服务健康状态
- 查询当前已加载能力
- 查询许可证状态
- 调用指定 AI capability 做推理
- 调用 agface 人脸比对组合接口

本文档以当前 `prod/web_service/main.py` 中已实现的真实接口为准。

---

## 2. 基础信息

## 2.1 服务地址

生产服务默认监听：

```text
http://<host>:8080
```

接口前缀统一为：

```text
/api/v1
```

例如：

```text
http://localhost:8080/api/v1/health
```

## 2.2 Content-Type 约定

- 查询类接口：`application/json`
- 图片推理接口：`multipart/form-data`
- Pipeline 创建/更新：`application/json`

## 2.3 鉴权说明

### 无需管理员 Token 的接口

以下接口通常可直接供第三方调用：

- `GET /api/v1/health`
- `GET /api/v1/capabilities`
- `GET /api/v1/license/status`
- `POST /api/v1/infer/{capability}`
- `POST /api/v1/agface/face_compare`
- `GET /api/v1/pipelines`
- `GET /api/v1/pipelines/{pipeline_id}`
- `POST /api/v1/pipelines/{pipeline_id}/validate`
- `POST /api/v1/pipeline/{pipeline_id}/run`

### 需要管理员 Token 的接口

以下接口需要：

```http
Authorization: Bearer <AI_ADMIN_TOKEN>
```

包括：

- `POST /api/v1/admin/reload`
- `POST /api/v1/admin/reload/{capability}`
- `GET /api/v1/admin/ab_tests`
- `POST /api/v1/admin/ab_tests/reload`
- `POST /api/v1/pipelines`
- `PUT /api/v1/pipelines/{pipeline_id}`
- `DELETE /api/v1/pipelines/{pipeline_id}`

---

## 3. 通用返回结构

## 3.1 通用推理成功返回

`POST /api/v1/infer/{capability}` 成功时统一返回：

```json
{
  "code": 0,
  "message": "success",
  "capability": "agface_face_detect",
  "model_version": "1.0.0",
  "inference_time_ms": 12.34,
  "result": {},
  "timestamp": "2026-04-23T16:00:00+08:00"
}
```

说明：

- `code = 0` 表示成功
- `result` 内部结构由具体 capability 决定
- `model_version` 来自 runtime 当前已加载的模型版本

## 3.2 通用失败返回

常见失败响应：

```json
{
  "code": 4004,
  "message": "Capability version not licensed",
  "capability": "agface_fake_photo"
}
```

或：

```json
{
  "code": 3001,
  "message": "Instance pool timeout or capability not available",
  "capability": "face_detect"
}
```

说明：

- HTTP 状态码与 `code` 一起判断
- `code` 为平台业务错误码
- `message` 为可读错误说明

---

## 4. 系统与状态接口

## 4.1 健康检查

### 接口

```http
GET /api/v1/health
```

### 作用

查询服务整体健康状态、GPU 可用性、已加载能力数、许可证状态。

### 示例返回

```json
{
  "status": "healthy",
  "capabilities": [
    {
      "capability": "agface_face_detect",
      "version": "1.0.0",
      "status": "loaded"
    }
  ],
  "license": {
    "status": "valid",
    "license_id": "LIC-XXXX",
    "valid_from": "2026-01-01T00:00:00+08:00",
    "valid_until": null,
    "days_remaining": -1,
    "capabilities": ["*"]
  },
  "server_time": "2026-04-23T16:00:00+08:00",
  "gpu_available": true,
  "runtime_initialized": true,
  "loaded_capability_count": 8,
  "discovered_model_capability_count": 8
}
```

### 字段说明

- `status`
  - `healthy` / `degraded`
- `gpu_available`
  - 是否检测到 GPU
- `license.days_remaining = -1`
  - 表示长期授权，不表示过期

---

## 4.2 查询当前已加载能力

### 接口

```http
GET /api/v1/capabilities
```

### 作用

返回当前 runtime 已加载 capability 列表，以及对应模型版本和 manifest。

### 示例返回

```json
{
  "capabilities": [
    {
      "capability": "agface_face_detect",
      "version": "1.0.0",
      "manifest": {
        "name": "agface_face_detect",
        "version": "1.0.0",
        "backend": "ncnn"
      }
    },
    {
      "capability": "desktop_recapture_detect",
      "version": "1.0.0",
      "manifest": {
        "name": "desktop_recapture_detect",
        "version": "1.0.0"
      }
    }
  ]
}
```

### 用途建议

第三方调用者在正式推理前，建议先调用本接口：

- 确认 capability 是否已加载
- 确认当前可用版本

---

## 4.3 查询能力诊断信息

### 接口

```http
GET /api/v1/capabilities/diagnostics
```

### 作用

用于诊断 capability 加载差异、模型目录缺失、运行时库路径等问题。

### 典型用途

- 模型目录排查
- so 加载排查
- 挂载路径排查
- `loaded_without_models` 排查

> 说明：本接口更适合运维与技术支持排障，不是普通业务调用必需接口。

---

## 4.4 查询许可证状态

### 接口

```http
GET /api/v1/license/status
```

### 作用

返回当前 prod runtime 使用的 license 状态。

### 示例返回

```json
{
  "status": "valid",
  "valid": true,
  "license_id": "LIC-XXXX",
  "valid_from": "2026-01-01T00:00:00+08:00",
  "valid_until": null,
  "days_remaining": -1,
  "version_constraint": ">=1.0.0",
  "capabilities": [
    "agface_face_detect",
    "agface_face_feature_glint512",
    "agface_fake_photo"
  ]
}
```

### 特别说明

- `days_remaining = -1`
  - 表示长期有效
- `valid_until = null`
  - 通常表示无截止时间
- `version_constraint`
  - 表示 capability 版本必须满足授权要求

---

## 5. 通用推理接口

## 5.1 调用任意 capability

### 接口

```http
POST /api/v1/infer/{capability}
```

### 说明

这是当前最核心的统一推理入口。大部分 capability 都通过该接口调用。

### Path 参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `capability` | string | capability 名称，例如 `agface_face_detect` |

### Form 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image` | file | 是 | 上传图片文件 |
| `options` | string | 否 | JSON 字符串，预留参数 |

### 请求示例

```bash
curl -X POST "http://localhost:8080/api/v1/infer/agface_face_detect" \
  -F "image=@test.jpg"
```

带 `options` 示例：

```bash
curl -X POST "http://localhost:8080/api/v1/infer/face_detect" \
  -F "image=@test.jpg" \
  -F 'options={"debug":true}'
```

### 成功返回示例

```json
{
  "code": 0,
  "message": "success",
  "capability": "agface_face_detect",
  "model_version": "1.0.0",
  "inference_time_ms": 15.62,
  "result": {
    "faces": [
      {
        "bbox": [120, 80, 160, 160],
        "score": 0.998
      }
    ]
  },
  "timestamp": "2026-04-23T16:00:00+08:00"
}
```

### 常见失败

#### capability 名非法

```json
{
  "detail": {
    "code": 2001,
    "message": "Invalid capability name"
  }
}
```

#### runtime 未初始化

```json
{
  "detail": {
    "code": 5001,
    "message": "Runtime not initialized"
  }
}
```

#### 授权版本不满足

```json
{
  "code": 4004,
  "message": "Capability version not licensed",
  "capability": "agface_fake_photo"
}
```

#### 能力未加载 / 实例池超时

```json
{
  "code": 3001,
  "message": "Instance pool timeout or capability not available",
  "capability": "face_detect"
}
```

---

## 6. agface 人脸比对接口

## 6.1 端到端人脸比对

### 接口

```http
POST /api/v1/agface/face_compare
```

### 作用

执行完整的人脸比对链路：

```text
detect -> crop -> feature_a -> feature_b -> cosine -> score
```

### Form 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `image_a` | file | 是 | - | 第一张人脸图片 |
| `image_b` | file | 是 | - | 第二张人脸图片 |
| `feature_model` | string | 否 | `agface_face_feature_glint512` | 特征提取 capability |
| `detector` | string | 否 | `agface_face_detect` | 检测 capability，传空或 `none` 表示跳过检测 |
| `margin_ratio` | float | 否 | `0.15` | 裁剪人脸时的边界扩展比例 |

### 允许的 `feature_model`

- `agface_face_feature_residual256`
- `agface_face_feature_glint512`
- `agface_face_feature_mobilenet256`

### 请求示例

```bash
curl -X POST "http://localhost:8080/api/v1/agface/face_compare" \
  -F "image_a=@face1.jpg" \
  -F "image_b=@face2.jpg" \
  -F "feature_model=agface_face_feature_glint512" \
  -F "detector=agface_face_detect" \
  -F "margin_ratio=0.15"
```

### 成功返回示例

```json
{
  "code": 0,
  "message": "success",
  "total_time_ms": 38.62,
  "feature_capability": "agface_face_feature_glint512",
  "detector_capability": "agface_face_detect",
  "faces": {
    "image_a": 1,
    "image_b": 1
  },
  "cosine": 0.823451,
  "score": 91.17,
  "dim": 512,
  "feature_a_sample": [0.012345, -0.032165, 0.004421],
  "feature_b_sample": [0.011928, -0.031991, 0.004770]
}
```

### 返回字段说明

| 字段 | 说明 |
|---|---|
| `cosine` | 原始余弦相似度 |
| `score` | 映射后的 0~100 分数 |
| `dim` | 特征维度 |
| `faces.image_a` | 第一张图检测到的人脸数 |
| `faces.image_b` | 第二张图检测到的人脸数 |

### 常见错误

#### feature capability 不在白名单

```json
{
  "detail": {
    "code": 1001,
    "message": "invalid feature_model; allowed: [...]"
  }
}
```

#### detector 或 feature capability 未加载

```json
{
  "detail": {
    "code": 2001,
    "message": "feature capability 'agface_face_feature_glint512' is not loaded",
    "loaded": ["agface_face_detect", "desktop_recapture_detect"]
  }
}
```

---

## 7. Pipeline 接口

> 说明：如果第三方只做单能力推理，可忽略本节。

## 7.1 列出 Pipeline

```http
GET /api/v1/pipelines
```

返回：

```json
{
  "pipelines": []
}
```

## 7.2 获取单个 Pipeline

```http
GET /api/v1/pipelines/{pipeline_id}
```

## 7.3 校验 Pipeline

```http
POST /api/v1/pipelines/{pipeline_id}/validate
```

返回：

```json
{
  "pipeline_id": "demo_pipeline",
  "valid": true,
  "errors": []
}
```

## 7.4 执行 Pipeline

```http
POST /api/v1/pipeline/{pipeline_id}/run
```

Form 参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image` | file | 是 | 输入图片 |
| `options` | string | 否 | 全局 JSON 选项 |

---

## 8. 管理接口

这些接口通常不开放给第三方业务调用，但便于交付与运维。

## 8.1 热重载全部能力

```http
POST /api/v1/admin/reload
Authorization: Bearer <AI_ADMIN_TOKEN>
```

## 8.2 热重载单个能力

```http
POST /api/v1/admin/reload/{capability}
Authorization: Bearer <AI_ADMIN_TOKEN>
```

## 8.3 查询 A/B 测试

```http
GET /api/v1/admin/ab_tests
Authorization: Bearer <AI_ADMIN_TOKEN>
```

## 8.4 重载 A/B 测试配置

```http
POST /api/v1/admin/ab_tests/reload
Authorization: Bearer <AI_ADMIN_TOKEN>
```

---

## 9. 当前已知 capability 清单

以下为当前仓库 `cpp/capabilities/` 中可识别的已知 capability 名称清单（不含内部公共目录 `_agface_common`）。

## 9.1 agface 系列

- `agface_barehead`
- `agface_face_detect`
- `agface_face_feature_glint512`
- `agface_face_feature_mobilenet256`
- `agface_face_feature_residual256`
- `agface_face_property`
- `agface_fake_photo`

## 9.2 人脸 / 人体 / 生物特征

- `face_3d_reconstruct`
- `face_attribute`
- `face_beautify`
- `face_desensitize`
- `face_detect`
- `face_landmark`
- `face_liveness_action`
- `face_liveness_silent`
- `face_quality`
- `face_recognition`
- `face_swap`
- `face_verify`
- `person_detect`
- `person_reid`
- `pose_estimate`
- `gesture_recognize`
- `body_action_recognize`
- `action_recognize`
- `liveness_anti_attack`
- `voice_liveness`
- `voiceprint_search`
- `voiceprint_verify`
- `speaker_diarize`
- `speech_emotion`

## 9.3 OCR / 证件 / 文档

- `ocr_bank_card`
- `ocr_business_license`
- `ocr_driver_license`
- `ocr_general`
- `ocr_handwriting`
- `ocr_invoice`
- `ocr_print`
- `ocr_signature`
- `ocr_table`
- `ocr_vehicle_license`
- `id_card_back_detect`
- `id_card_classify`
- `id_card_front_detect`
- `id_card_ocr`
- `passport_cn_ocr`
- `passport_intl_ocr`
- `hk_macao_permit_ocr`
- `household_register_ocr`
- `social_security_ocr`
- `doc_classify`
- `doc_classify_rpa`
- `doc_rectify`
- `form_extract`
- `bill_verify`
- `contract_amount`
- `contract_extract`
- `contract_party`
- `contract_seal_detect`
- `contract_sign_locate`
- `contract_summary`
- `eseal_detect`
- `eseal_verify`
- `seal_recognize`
- `signature_compare`

## 9.4 图像 / 视频 / 内容安全

- `desktop_recapture_detect`
- `recapture_detect`
- `deepfake_detect`
- `content_compliance`
- `image_classify`
- `image_dehaze`
- `image_denoise`
- `image_enhance`
- `image_inpaint`
- `image_retrieval`
- `image_super_res`
- `image_tamper_detect`
- `watermark_extract`
- `object_detect`
- `instance_segment`
- `panoptic_segment`
- `semantic_segment`
- `scene_text_detect`
- `vehicle_detect`
- `vehicle_attribute`
- `logo_recognize`
- `product_recognize`
- `crowd_count`
- `video_condense`
- `video_frame_extract`
- `video_summarize`
- `video_tamper_detect`
- `video_track`

## 9.5 音频 / 语音

- `asr`
- `asr_punct_restore`
- `audio_denoise`
- `audio_fingerprint`
- `tts`
- `vocal_separate`

## 9.6 NLP / 文本理解

- `entity_link`
- `intent_recognize`
- `keyword_extract`
- `language_identify`
- `ner`
- `pos_tag`
- `sensitive_detect`
- `sentiment_analyze`
- `slot_fill`
- `text_classify`
- `text_correct`
- `text_extract`
- `text_segment`
- `text_similarity`
- `text_summarize`

## 9.7 其他

- `doc_classify`
- `doc_classify_rpa`
- `plate_recognize`

> 注意：
> 
> - “已知 capability” 不等于“当前 prod 已加载 capability”。
> - 实际可调用能力，以 `GET /api/v1/capabilities` 返回结果为准。

---

## 10. 第三方接入建议

建议第三方接入按以下顺序进行：

1. 调用 `GET /api/v1/health`
   - 确认服务可用
2. 调用 `GET /api/v1/capabilities`
   - 确认目标 capability 已加载
3. 调用 `GET /api/v1/license/status`
   - 确认授权状态正常
4. 调用 `POST /api/v1/infer/{capability}`
   - 执行单能力推理
5. 如做人脸比对，使用 `POST /api/v1/agface/face_compare`

---

## 11. 常见问题

## 11.1 为什么 license 显示 `days_remaining = -1`，但接口仍能正常调用？

因为：

- `-1` 在当前系统中表示 **长期有效 / 无截止日期**
- 不表示过期

第三方如需展示，可按以下规则处理：

- `days_remaining == -1` -> 显示“长期有效”

## 11.2 如何知道某个 capability 当前是否真的能调用？

请调用：

```http
GET /api/v1/capabilities
```

只有该接口返回的 capability，才表示当前 runtime 已加载。

## 11.3 不同 capability 的 `result` 为什么结构不同？

因为：

- 平台统一使用 `POST /api/v1/infer/{capability}` 作为通用入口
- 但每个 capability 的业务结果不同
- 因此 `result` 字段是 capability-specific 的

如果需要对某个 capability 做更细的字段约定，可在本文件基础上继续补充专项文档。

---

## 12. 变更记录

| 版本 | 日期 | 内容 |
|---|---|---|
| v1.0 | 2026-04-23 | 初版第三方生产接口文档，覆盖系统状态、通用推理、agface 比对、pipeline 与 capability 清单 |
