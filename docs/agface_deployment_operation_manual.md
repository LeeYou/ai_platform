# agface 模型部署与 `manifest.json` 操作手册

**北京爱知之星科技股份有限公司 (Agile Star)**
**版本:** v1.0 | **日期:** 2026-04-22

---

## 1. 文档目标

本文档用于指导你在 `ai_platform` 生产环境中完成 `agface_*` 系列能力的完整部署，包括：

- `manifest.json` 的完整字段和示例
- 每个 `agface` 能力所需模型文件清单
- 宿主机路径与容器内路径的对应关系
- `libs` / `models` / `licenses` 的标准目录结构
- 从旧 `ai_agface` 工程迁移模型的操作方式
- 如何验证模型、动态库、授权是否都正确生效
- 常见错误的定位方法

本文档适合以下角色：

- 部署同学
- 运维同学
- 交付同学
- 平台对接开发同学

---

## 2. 适用 capability 范围

当前已落地并可构建的 `agface_*` capability 包括：

- `agface_face_detect`
- `agface_face_feature_residual256`
- `agface_face_feature_glint512`
- `agface_face_feature_mobilenet256`
- `agface_barehead`
- `agface_fake_photo`
- `agface_face_property`

这些 capability 的共同点：

- 基于 `Ai*` C ABI 导出
- 由 `libai_runtime.so` 动态加载
- `AiCreate(model_dir, config_json)` 接收模型目录
- 运行时会依赖模型目录中的 `manifest.json`
- 后端统一为 `ncnn`

---

## 3. 生产环境目录与挂载关系

## 3.1 宿主机目录标准

生产环境宿主机建议统一使用：

```text
/data/ai_platform/
├─ models/
├─ libs/
├─ licenses/
├─ pipelines/
└─ logs/
```

各目录含义：

- `models/`
  - capability 模型包目录
- `libs/`
  - builder 编译输出的 capability 动态库目录
- `licenses/`
  - 授权文件与公钥文件
- `pipelines/`
  - pipeline 编排配置
- `logs/`
  - prod 日志

## 3.2 `docker-compose.prod.yml` 挂载关系

生产 compose 的挂载关系如下：

| 资源 | 宿主机路径 | 容器内路径 |
|---|---|---|
| 模型 | `/data/ai_platform/models` | `/mnt/ai_platform/models` |
| 动态库 | `/data/ai_platform/libs/${AI_ARCH:-linux_x86_64}` | `/mnt/ai_platform/libs` |
| 授权 | `/data/ai_platform/licenses` | `/mnt/ai_platform/licenses` |
| pipelines | `/data/ai_platform/pipelines` | `/mnt/ai_platform/pipelines` |
| 日志 | `/data/ai_platform/logs/prod` | `/mnt/ai_platform/logs` |

因此，prod 容器内真正读取的是：

- 模型：`/mnt/ai_platform/models/<capability>/current/`
- 动态库：`/mnt/ai_platform/libs/<capability>/current/lib/`
- 授权：`/mnt/ai_platform/licenses/license.bin`
- 公钥：`/mnt/ai_platform/licenses/pubkey.pem`

## 3.3 资源读取优先级

prod 运行时遵循：

```text
/mnt/ai_platform > /app
```

即：

- 优先读取挂载目录
- 挂载目录不存在时，才回退镜像内置目录

---

## 4. 动态库目录标准

每个 capability 在宿主机的推荐目录：

```text
/data/ai_platform/libs/linux_x86_64/<capability>/current/lib/
```

标准结构示例：

```text
/data/ai_platform/libs/linux_x86_64/agface_fake_photo/current/lib/
├─ libagface_fake_photo.so
├─ libagface_fake_photo.so.1
├─ libagface_fake_photo.so.1.0.0
├─ libai_runtime.so
├─ libai_runtime.so.1
└─ libai_runtime.so.1.0.0
```

在 prod 容器中，该目录会显示为：

```text
/mnt/ai_platform/libs/agface_fake_photo/current/lib/
```

动态库校验重点：

- `lib<capability>.so` 存在
- `libai_runtime.so` 存在
- `ldd lib<capability>.so` 不应出现 `not found`

---

## 5. 模型目录标准

每个 capability 的模型推荐目录：

```text
/data/ai_platform/models/<capability>/<version>/
/data/ai_platform/models/<capability>/current -> <version>
```

示例：

```text
/data/ai_platform/models/agface_fake_photo/1.0.0/
/data/ai_platform/models/agface_fake_photo/current -> 1.0.0
```

prod 容器内对应路径：

```text
/mnt/ai_platform/models/agface_fake_photo/current/
```

重要要求：

- `current` 必须存在
- `current/manifest.json` 必须存在
- capability 所要求的全部 `.param/.bin` 必须齐全

---

## 6. 授权目录标准

宿主机目录：

```text
/data/ai_platform/licenses/
├─ license.bin
└─ pubkey.pem
```

容器内目录：

```text
/mnt/ai_platform/licenses/
├─ license.bin
└─ pubkey.pem
```

说明：

- `license.bin` 是客户授权文件
- `pubkey.pem` 用于校验授权签名

---

## 7. `manifest.json` 通用字段说明

agface 通用 manifest 解析字段来源于 `_agface_common/include/agface/manifest.h` 与迁移脚本。

## 7.1 通用字段列表

| 字段 | 是否必需 | 说明 |
|---|---|---|
| `name` | 是 | capability 名称 |
| `version` | 是 | 模型版本，建议 `1.0.0` 或更高 |
| `backend` | 是 | 固定为 `ncnn` |
| `description` | 建议 | 模型描述 |
| `company` | 建议 | 建议填 `agilestar.cn` |
| `param_file` | 是 | NCNN param 文件相对路径 |
| `bin_file` | 是 | NCNN bin 文件相对路径 |
| `input.blob` | 建议 | 输入 blob 名 |
| `input.base_size` | 建议 | 输入基准尺寸 |
| `input.color` | 建议 | 输入颜色空间 |
| `input.mean` | 建议 | 归一化 mean |
| `input.norm` | 建议 | 归一化 norm |
| `output.blob` | 建议 | 输出 blob 名 |
| `output.format` | 建议 | 输出格式 |
| `thresholds.score` | 可选 | 检测分数阈值 |
| `thresholds.min_face` | 可选 | 最小人脸 |
| `thresholds.max_image_dim` | 可选 | 最大输入边长 |
| `feature_dim` | feature 类必需 | 特征维度 |
| `entry` | legacy vision 类建议 | 入口信息 |
| `checksum_sha256` | 强烈建议 | 文件校验表 |

## 7.2 版本字段特别注意

prod runtime 会从 `manifest.json` 中读取：

- `model_version`
- 若不存在，再读取 `version`

如果 `manifest.json` 缺失，runtime 会把版本记为：

```text
unknown
```

当 license 带版本约束，例如：

```text
>=1.0.0
```

就会报错：

```json
{
  "code": 4004,
  "message": "Capability version not licensed"
}
```

所以：

- `manifest.json` 必须存在
- `version` 必须是合法版本号，建议至少 `1.0.0`

---

## 8. 各 capability 模型目录与完整 manifest 示例

以下示例是交付模板。`checksum_sha256` 中的值请替换为真实 SHA-256，或直接使用迁移脚本自动生成。

## 8.1 `agface_face_detect`

### 模型目录

```text
/data/ai_platform/models/agface_face_detect/1.0.0/
├─ manifest.json
├─ detection.param
└─ detection.bin
```

### `current`

```text
/data/ai_platform/models/agface_face_detect/current -> 1.0.0
```

### 旧模型来源

```text
<src>/delivery_package/models/detection/detection.param
<src>/delivery_package/models/detection/detection.bin
```

或：

```text
<src>/models/detection/detection.param
<src>/models/detection/detection.bin
```

### 完整 manifest

```json
{
  "name": "agface_face_detect",
  "version": "1.0.0",
  "backend": "ncnn",
  "description": "agface 人脸检测（NCNN RetinaFace/SSD 头）。迁移自 ai_agface V5 detection.param/bin。与 ai_agface FaceDetectRetina 的推理流程等价。",
  "company": "agilestar.cn",
  "param_file": "detection.param",
  "bin_file": "detection.bin",
  "input": {
    "blob": "data",
    "base_size": 192,
    "color": "BGR",
    "mean": [104.0, 117.0, 123.0],
    "norm": [1.0, 1.0, 1.0]
  },
  "output": {
    "blob": "detection_out",
    "format": "ssd"
  },
  "thresholds": {
    "score": 0.5,
    "min_face": 40,
    "max_image_dim": 1200
  },
  "checksum_sha256": {
    "detection.param": "<SHA256_OF_detection.param>",
    "detection.bin": "<SHA256_OF_detection.bin>"
  }
}
```

## 8.2 `agface_face_feature_residual256`

### 模型目录

```text
/data/ai_platform/models/agface_face_feature_residual256/1.0.0/
├─ manifest.json
├─ model.param
└─ model.bin
```

### 旧模型来源

```text
<src>/delivery_package/models/residual/residual.param
<src>/delivery_package/models/residual/residual.bin
```

或：

```text
<src>/models/residual/residual.param
<src>/models/residual/residual.bin
```

### 完整 manifest

```json
{
  "name": "agface_face_feature_residual256",
  "version": "1.0.0",
  "backend": "ncnn",
  "description": "agface 人脸特征 (NCNN Residual 256-dim)。迁移自 ai_agface V5 residual/residual.{param,bin}。",
  "company": "agilestar.cn",
  "param_file": "model.param",
  "bin_file": "model.bin",
  "feature_dim": 256,
  "input": {
    "blob": "data",
    "base_size": 112,
    "color": "RGB",
    "mean": [127.5, 127.5, 127.5],
    "norm": [0.0078125, 0.0078125, 0.0078125]
  },
  "output": {
    "blob": "pre_fc1",
    "format": "embedding"
  },
  "checksum_sha256": {
    "model.param": "<SHA256_OF_model.param>",
    "model.bin": "<SHA256_OF_model.bin>"
  }
}
```

## 8.3 `agface_face_feature_glint512`

### 模型目录

```text
/data/ai_platform/models/agface_face_feature_glint512/1.0.0/
├─ manifest.json
├─ model.param
└─ model.bin
```

### 旧模型来源

```text
<src>/delivery_package/models/glint360k_r34/glint360k_r34.opt.param
<src>/delivery_package/models/glint360k_r34/glint360k_r34.opt.bin
```

或：

```text
<src>/models/glint360k_r34/glint360k_r34.opt.param
<src>/models/glint360k_r34/glint360k_r34.opt.bin
```

### 完整 manifest

```json
{
  "name": "agface_face_feature_glint512",
  "version": "1.0.0",
  "backend": "ncnn",
  "description": "agface 人脸特征 (NCNN Glint360K-R34 512-dim)。迁移自 ai_agface V5 glint360k_r34/glint360k_r34.opt.{param,bin}。",
  "company": "agilestar.cn",
  "param_file": "model.param",
  "bin_file": "model.bin",
  "feature_dim": 512,
  "input": {
    "blob": "data",
    "base_size": 112,
    "color": "RGB",
    "mean": [127.5, 127.5, 127.5],
    "norm": [0.0078125, 0.0078125, 0.0078125]
  },
  "output": {
    "blob": "pre_fc1",
    "format": "embedding"
  },
  "checksum_sha256": {
    "model.param": "<SHA256_OF_model.param>",
    "model.bin": "<SHA256_OF_model.bin>"
  }
}
```

## 8.4 `agface_face_feature_mobilenet256`

### 模型目录

```text
/data/ai_platform/models/agface_face_feature_mobilenet256/1.0.0/
├─ manifest.json
├─ model.param
└─ model.bin
```

### 旧模型来源

```text
<src>/delivery_package/models/mobilefacenet_fc_256/mobilefacenet_fc_256.param
<src>/delivery_package/models/mobilefacenet_fc_256/mobilefacenet_fc_256.bin
```

或：

```text
<src>/models/mobilefacenet_fc_256/mobilefacenet_fc_256.param
<src>/models/mobilefacenet_fc_256/mobilefacenet_fc_256.bin
```

### 完整 manifest

```json
{
  "name": "agface_face_feature_mobilenet256",
  "version": "1.0.0",
  "backend": "ncnn",
  "description": "agface 人脸特征 (NCNN MobileFaceNet 256-dim, output=fc1)。迁移自 ai_agface V5 mobilefacenet_fc_256/mobilefacenet_fc_256.{param,bin}。",
  "company": "agilestar.cn",
  "param_file": "model.param",
  "bin_file": "model.bin",
  "feature_dim": 256,
  "input": {
    "blob": "data",
    "base_size": 112,
    "color": "RGB",
    "mean": [127.5, 127.5, 127.5],
    "norm": [0.0078125, 0.0078125, 0.0078125]
  },
  "output": {
    "blob": "fc1",
    "format": "embedding"
  },
  "checksum_sha256": {
    "model.param": "<SHA256_OF_model.param>",
    "model.bin": "<SHA256_OF_model.bin>"
  }
}
```

## 8.5 `agface_barehead`

### 模型目录

```text
/data/ai_platform/models/agface_barehead/1.0.0/
├─ manifest.json
└─ detection/
   ├─ detection.param
   ├─ detection.bin
   ├─ det3.param
   ├─ det3.bin
   ├─ modelht.param
   └─ modelht.bin
```

### 完整 manifest

```json
{
  "name": "agface_barehead",
  "version": "1.0.0",
  "backend": "ncnn",
  "description": "agface 裸头检测（NCNN legacy barehead），迁移自 ai_agface barehead_module。",
  "company": "agilestar.cn",
  "param_file": "detection/detection.param",
  "bin_file": "detection/detection.bin",
  "input": {
    "blob": "data",
    "base_size": 192,
    "color": "BGR",
    "mean": [104.0, 117.0, 123.0],
    "norm": [1.0, 1.0, 1.0]
  },
  "output": {
    "blob": "legacy_vision_bundle",
    "format": "legacy_vision_bundle"
  },
  "entry": {
    "kind": "legacy_vision_bundle",
    "detector": "detection/detection.param"
  },
  "checksum_sha256": {
    "detection/detection.param": "<SHA256>",
    "detection/detection.bin": "<SHA256>",
    "detection/det3.param": "<SHA256>",
    "detection/det3.bin": "<SHA256>",
    "detection/modelht.param": "<SHA256>",
    "detection/modelht.bin": "<SHA256>"
  }
}
```

## 8.6 `agface_fake_photo`

### 模型目录

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

### 完整 manifest

```json
{
  "name": "agface_fake_photo",
  "version": "1.0.0",
  "backend": "ncnn",
  "description": "agface 翻拍照检测（NCNN legacy fake_photo），迁移自 ai_agface fake_photo_module。",
  "company": "agilestar.cn",
  "param_file": "detection/detection.param",
  "bin_file": "detection/detection.bin",
  "input": {
    "blob": "data",
    "base_size": 192,
    "color": "BGR",
    "mean": [104.0, 117.0, 123.0],
    "norm": [1.0, 1.0, 1.0]
  },
  "output": {
    "blob": "legacy_vision_bundle",
    "format": "legacy_vision_bundle"
  },
  "entry": {
    "kind": "legacy_vision_bundle",
    "detector": "detection/detection.param"
  },
  "checksum_sha256": {
    "detection/detection.param": "<SHA256>",
    "detection/detection.bin": "<SHA256>",
    "detection/det3.param": "<SHA256>",
    "detection/det3.bin": "<SHA256>",
    "detection/model_1.param": "<SHA256>",
    "detection/model_1.bin": "<SHA256>",
    "detection/model_2.param": "<SHA256>",
    "detection/model_2.bin": "<SHA256>",
    "detection/model_3.param": "<SHA256>",
    "detection/model_3.bin": "<SHA256>",
    "detection/yolov7s320face.param": "<SHA256>",
    "detection/yolov7s320face.bin": "<SHA256>"
  }
}
```

## 8.7 `agface_face_property`

### 模型目录

```text
/data/ai_platform/models/agface_face_property/1.0.0/
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

### 完整 manifest

```json
{
  "name": "agface_face_property",
  "version": "1.0.0",
  "backend": "ncnn",
  "description": "agface 人脸属性检测（NCNN legacy face_property），迁移自 ai_agface face_property_module。",
  "company": "agilestar.cn",
  "param_file": "detection/detection.param",
  "bin_file": "detection/detection.bin",
  "input": {
    "blob": "data",
    "base_size": 192,
    "color": "BGR",
    "mean": [104.0, 117.0, 123.0],
    "norm": [1.0, 1.0, 1.0]
  },
  "output": {
    "blob": "legacy_vision_bundle",
    "format": "legacy_vision_bundle"
  },
  "entry": {
    "kind": "legacy_vision_bundle",
    "detector": "detection/detection.param"
  },
  "checksum_sha256": {
    "detection/detection.param": "<SHA256>",
    "detection/detection.bin": "<SHA256>",
    "detection/det3.param": "<SHA256>",
    "detection/det3.bin": "<SHA256>",
    "detection/model_1.param": "<SHA256>",
    "detection/model_1.bin": "<SHA256>",
    "detection/model_2.param": "<SHA256>",
    "detection/model_2.bin": "<SHA256>",
    "detection/model_3.param": "<SHA256>",
    "detection/model_3.bin": "<SHA256>",
    "detection/modelht.param": "<SHA256>",
    "detection/modelht.bin": "<SHA256>",
    "detection/yolov7s320face.param": "<SHA256>",
    "detection/yolov7s320face.bin": "<SHA256>",
    "detection/face_landmark_with_attention.param": "<SHA256>",
    "detection/face_landmark_with_attention.bin": "<SHA256>"
  }
}
```

---

## 9. 推荐迁移脚本

仓库里已有以下脚本：

- `scripts/migrate_agface_face_detect_model.py`
- `scripts/migrate_agface_face_feature_models.py`
- `scripts/migrate_agface_vision_models.py`

## 9.1 face_detect

```bash
python scripts/migrate_agface_face_detect_model.py \
  --src "H:/work/训练数据/caffe-base/ai_agface" \
  --dst "/data/ai_platform/models" \
  --version 1.0.0 \
  --overwrite
```

## 9.2 face_feature

```bash
python scripts/migrate_agface_face_feature_models.py \
  --src "H:/work/训练数据/caffe-base/ai_agface" \
  --dst "/data/ai_platform/models" \
  --version 1.0.0 \
  --which all \
  --overwrite
```

## 9.3 legacy vision

```bash
python scripts/migrate_agface_vision_models.py \
  --src "H:/work/训练数据/caffe-base/ai_agface" \
  --dst "/data/ai_platform/models" \
  --version 1.0.0 \
  --which all \
  --overwrite
```

---

## 10. 标准部署步骤

## 10.1 准备目录

```bash
mkdir -p /data/ai_platform/models
mkdir -p /data/ai_platform/libs/linux_x86_64
mkdir -p /data/ai_platform/licenses
mkdir -p /data/ai_platform/logs/prod
```

## 10.2 编译 capability

通过 build 管理页面或 builder 容器编译对应 capability，确保生成：

```text
/data/ai_platform/libs/linux_x86_64/<capability>/current/lib/
```

## 10.3 迁移模型

使用上面的迁移脚本生成：

```text
/data/ai_platform/models/<capability>/<version>/
```

## 10.4 创建 `current`

```bash
cd /data/ai_platform/models/<capability>
ln -sfn <version> current
```

## 10.5 准备 license

确保：

```text
/data/ai_platform/licenses/license.bin
/data/ai_platform/licenses/pubkey.pem
```

## 10.6 重建 prod

```bash
docker compose -f docker-compose.prod.yml up -d --build prod
```

## 10.7 查看日志

```bash
docker compose -f docker-compose.prod.yml logs -f prod
```

---

## 11. 推荐验证方法

## 11.1 检查模型目录

```bash
ls -R /data/ai_platform/models/agface_fake_photo/current
```

## 11.2 检查动态库目录

```bash
ls -R /data/ai_platform/libs/linux_x86_64/agface_fake_photo/current/lib
```

## 11.3 检查容器内动态依赖

```bash
docker exec -it ai-prod bash
ldconfig -p | grep opencv
ldd /mnt/ai_platform/libs/agface_fake_photo/current/lib/libagface_fake_photo.so
```

## 11.4 检查授权状态

```bash
curl http://localhost:8080/api/v1/license/status
```

重点查看：

- `capabilities`
- `version_constraint`

## 11.5 检查 runtime 能力版本

```bash
curl http://localhost:8080/api/v1/capabilities
```

重点查看：

- `capability`
- `version`

## 11.6 检查详细诊断

```bash
curl http://localhost:8080/api/v1/capabilities/diagnostics
```

重点查看：

- `loaded_capabilities`
- `loaded_without_models`
- `discovered_model_capabilities`
- `loaded_capability_details[*].version`
- `loaded_capability_details[*].build_info`

---

## 12. 常见问题排查

## 12.1 报错：`Capability version not licensed`

典型原因：

- `license` 已授权该 capability
- 但 runtime 读取到的 capability 版本是 `unknown`

通常是因为：

- `current/manifest.json` 缺失
- `current` 指向错误目录
- `manifest.json` 中没有合法 `version`

处理方法：

- 检查 `/data/ai_platform/models/<capability>/current/manifest.json`
- 检查 `/api/v1/capabilities` 返回的 `version`
- 确保 `version >= 1.0.0`

## 12.2 报错：`Capability not found or not loaded`

通常是：

- 对应 `.so` 没编出来
- `current/lib/lib<capability>.so` 不存在
- `dlopen` 失败

处理方法：

- 检查 `/data/ai_platform/libs/linux_x86_64/<capability>/current/lib/`
- 检查 `docker logs`
- 检查 `ldd lib<capability>.so`

## 12.3 报错：`undefined symbol`

通常是：

- capability 静态库/公共库漏编译
- 新 `.so` 没真正同步到宿主机或 prod 未重启

## 12.4 报错：`libopencv_*.so => not found`

通常是：

- prod 镜像缺 OpenCV runtime 依赖

处理方法：

- 在 prod Dockerfile 中安装对应 runtime 包
- 进入容器执行 `ldconfig -p | grep opencv`

## 12.5 `loaded_without_models` 包含 agface capability

说明：

- capability `.so` 已加载
- 但模型目录没有被资源扫描器识别到

通常是：

- `current` 缺失
- `manifest.json` 缺失
- 模型目录层级不对

---

## 13. 速查表

| capability | 模型根目录结构 | 关键文件 |
|---|---|---|
| `agface_face_detect` | 根目录平铺 | `manifest.json`, `detection.param`, `detection.bin` |
| `agface_face_feature_residual256` | 根目录平铺 | `manifest.json`, `model.param`, `model.bin` |
| `agface_face_feature_glint512` | 根目录平铺 | `manifest.json`, `model.param`, `model.bin` |
| `agface_face_feature_mobilenet256` | 根目录平铺 | `manifest.json`, `model.param`, `model.bin` |
| `agface_barehead` | `detection/` 子目录 | `manifest.json`, `detection/detection.*`, `detection/det3.*`, `detection/modelht.*` |
| `agface_fake_photo` | `detection/` 子目录 | `manifest.json`, `detection/detection.*`, `detection/det3.*`, `detection/model_1/2/3.*`, `detection/yolov7s320face.*` |
| `agface_face_property` | `detection/` 子目录 | `manifest.json`, `detection/detection.*`, `detection/det3.*`, `detection/model_1/2/3.*`, `detection/modelht.*`, `detection/yolov7s320face.*`, `detection/face_landmark_with_attention.*` |

---

## 14. 相关现有文档

如果你还需要更简版说明，可同时参考：

- `docs/agface_capability_model_manual.md`

本文件是面向生产交付与排障的详细操作版。
