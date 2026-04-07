# 生产镜像动态能力扩展与更新指南

**北京爱知之星科技股份有限公司 (Agile Star)**
**文档版本：v1.0 | 2026-04-02**

---

## 目录

1. [概述](#1-概述)
2. [设计原则](#2-设计原则)
3. [目录结构规范](#3-目录结构规范)
4. [新增AI能力部署流程](#4-新增ai能力部署流程)
5. [GPU优先CPU兜底策略](#5-gpu优先cpu兜底策略)
6. [热重载机制](#6-热重载机制)
7. [验证与测试](#7-验证与测试)
8. [常见问题FAQ](#8-常见问题faq)

---

## 1. 概述

### 1.1 核心目标

生产镜像设计遵循**"挂载优先于内置"**原则,实现以下目标:

1. **无需重新构建镜像** - 新增AI能力只需挂载SO库和模型文件
2. **动态能力发现** - Runtime自动扫描挂载目录,发现并加载新能力
3. **热重载支持** - 更新后可触发热重载,无需重启容器
4. **GPU优先策略** - 自动检测GPU,GPU可用时使用CUDA加速,不可用时自动回退CPU

### 1.2 适用场景

- **生产环境能力扩展** - 已交付客户的生产系统需要新增AI能力
- **能力版本更新** - 已有能力的模型或SO库需要升级
- **多能力组合部署** - 一次性部署多个AI能力

---

## 2. 设计原则

### 2.1 资源加载优先级

```
宿主机挂载目录 > 镜像内置目录
```

Runtime在启动时按以下顺序查找资源:

1. **优先**: 宿主机挂载目录 `/mnt/ai_platform/`
2. **回退**: 镜像内置目录 `/app/`

这保证了:
- 镜像开箱即用(内置默认能力)
- 挂载覆盖内置(现场更新无需重新打包镜像)

### 2.2 GPU优先CPU兜底

**重要说明**: 生产镜像基于 `ubuntu:22.04` (CPU-only),GPU加速能力在编译的SO库中实现。

SO库编译时链接CUDA 11.8 Runtime和ONNXRuntime GPU Provider,并内置GPU检测逻辑:

- **编译阶段** - 使用 `agilestar/ai-builder` (CUDA 11.8) 编译SO库,链接CUDA支持
- **运行阶段** - SO库在AiInit时检测GPU可用性:
  - GPU可用 → 加载CUDA Provider,使用GPU加速
  - GPU不可用 → 自动回退CPU Provider,功能正常
- **容器无需CUDA** - 生产容器仅加载SO文件,GPU检测由SO内部完成

```cpp
// C++ SO内部GPU优先策略 (编译时链接CUDA 11.8)
OrtStatus* status = api->SessionOptionsAppendExecutionProvider_CUDA(session_opts, &cuda_options);
if (status == nullptr) {
    fprintf(stdout, "[capability] GPU mode enabled\n");  // GPU可用
} else {
    fprintf(stderr, "[capability] CUDA unavailable, using CPU\n");  // 回退CPU
    api->ReleaseStatus(status);
}
```

这种设计的优势:
- ✅ 生产容器保持轻量(无需CUDA镜像)
- ✅ SO库在有GPU的环境自动加速
- ✅ SO库在无GPU的环境正常运行
- ✅ 同一个SO文件适配GPU和CPU环境

### 2.3 实例池架构

推理使用C++ Runtime实例池,而非每次请求创建新实例:

```python
# ✅ 正确实现(使用实例池,生产级性能)
handle = runtime.acquire(capability, timeout_ms=30000)
result = runtime.infer(handle, image_data, width, height, channels)
runtime.release(handle)

# ❌ 错误实现(每次创建新实例,性能差)
cap = AiCapability(so_path)
cap.create(model_dir)
cap.init()
result = cap.infer(...)
cap.destroy()
```

---

## 3. 目录结构规范

### 3.1 宿主机挂载目录

```bash
/data/ai_platform/
├── libs/                           # SO库目录
│   └── linux_x86_64/               # Linux x86_64平台
│       ├── desktop_recapture_detect/   # 能力1
│       │   ├── lib/
│       │   │   ├── libai_runtime.so -> libai_runtime.so.1
│       │   │   ├── libai_runtime.so.1 -> libai_runtime.so.1.0.0
│       │   │   ├── libai_runtime.so.1.0.0
│       │   │   ├── libdesktop_recapture_detect.so -> libdesktop_recapture_detect.so.1
│       │   │   ├── libdesktop_recapture_detect.so.1 -> libdesktop_recapture_detect.so.1.0.0
│       │   │   └── libdesktop_recapture_detect.so.1.0.0
│       │   └── include/            # C++头文件(可选)
│       └── face_detect/            # 能力2
│           └── lib/
│               ├── libai_runtime.so (符号链接)
│               └── libface_detect.so
│
├── models/                         # 模型目录
│   ├── desktop_recapture_detect/
│   │   ├── v1.0.0/
│   │   │   ├── model.onnx
│   │   │   ├── manifest.json
│   │   │   ├── preprocess.json
│   │   │   └── labels.json
│   │   └── current -> v1.0.0      # 符号链接指向当前版本
│   └── face_detect/
│       ├── v1.0.0/
│       └── current -> v1.0.0
│
└── licenses/                       # 授权文件
    ├── license.bin                 # RSA-2048签名授权
    └── pubkey.pem                  # 公钥(用于签名验证)
```

### 3.2 Docker挂载配置

```yaml
# docker-compose.prod.yml
services:
  ai-prod:
    image: agilestar/ai-prod:latest
    runtime: nvidia  # 启用GPU支持
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility
    volumes:
      - /data/ai_platform/libs:/mnt/ai_platform/libs:ro
      - /data/ai_platform/models:/mnt/ai_platform/models:ro
      - /data/ai_platform/licenses:/mnt/ai_platform/licenses:ro
      - /data/ai_platform/logs/prod:/mnt/ai_platform/logs:rw
```

---

## 4. 新增AI能力部署流程

### 4.1 前置条件

1. AI能力已完成训练,ONNX模型已导出
2. AI能力的C++ SO库已通过ai-builder编译
3. 授权文件包含新能力名称

### 4.2 部署步骤

#### 步骤1: 准备模型包

```bash
# 在宿主机上创建模型目录
mkdir -p /data/ai_platform/models/new_capability/v1.0.0

# 复制模型文件
cp model.onnx /data/ai_platform/models/new_capability/v1.0.0/
cp manifest.json /data/ai_platform/models/new_capability/v1.0.0/
cp preprocess.json /data/ai_platform/models/new_capability/v1.0.0/
cp labels.json /data/ai_platform/models/new_capability/v1.0.0/

# 创建current符号链接
cd /data/ai_platform/models/new_capability
ln -s v1.0.0 current
```

**manifest.json示例:**

```json
{
  "capability": "new_capability",
  "model_version": "1.0.0",
  "framework": "pytorch",
  "onnx_opset": 14,
  "input_shape": [1, 3, 224, 224],
  "output_shape": [1, 1000],
  "labels_file": "labels.json",
  "preprocess_file": "preprocess.json"
}
```

#### 步骤2: 部署SO库

```bash
# 从ai-builder编译输出复制SO库
# 源路径(ai-builder输出): /workspace/output/linux_x86_64/new_capability/lib/
# 目标路径(宿主机):      /data/ai_platform/libs/linux_x86_64/new_capability/lib/

mkdir -p /data/ai_platform/libs/linux_x86_64/new_capability/lib

# 复制SO库及符号链接
cp -P /workspace/output/linux_x86_64/new_capability/lib/* \
   /data/ai_platform/libs/linux_x86_64/new_capability/lib/

# 验证SO库
ls -l /data/ai_platform/libs/linux_x86_64/new_capability/lib/
# 应输出:
# libai_runtime.so -> libai_runtime.so.1
# libai_runtime.so.1 -> libai_runtime.so.1.0.0
# libai_runtime.so.1.0.0
# libnew_capability.so -> libnew_capability.so.1
# libnew_capability.so.1 -> libnew_capability.so.1.0.0
# libnew_capability.so.1.0.0
```

#### 步骤3: 更新授权文件

```bash
# 授权文件必须包含新能力名称
# license.bin由授权子系统生成,包含RSA-2048签名

# 检查授权内容(Python脚本)
python3 <<EOF
import json
with open('/data/ai_platform/licenses/license.bin', encoding='utf-8') as f:
    lic = json.load(f)
    print("Authorized capabilities:", lic.get("capabilities"))
    # 应包含: ["desktop_recapture_detect", "face_detect", "new_capability"]
EOF
```

#### 步骤4: 触发热重载

```bash
# 方法1: 调用热重载API(推荐)
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"

# 方法2: 重启容器(简单但服务中断)
docker-compose restart ai-prod
```

#### 步骤5: 验证新能力

```bash
# 检查健康状态
curl http://localhost:8080/api/v1/health | jq .

# 应输出包含新能力:
# {
#   "status": "healthy",
#   "capabilities": [
#     {"capability": "desktop_recapture_detect", "version": "1.0.0", "status": "loaded"},
#     {"capability": "face_detect", "version": "1.0.0", "status": "loaded"},
#     {"capability": "new_capability", "version": "1.0.0", "status": "loaded"}
#   ],
#   "gpu_available": true
# }

# 测试推理
curl -X POST http://localhost:8080/api/v1/infer/new_capability \
  -F "image=@test_image.jpg" | jq .
```

---

## 5. GPU优先CPU兜底策略

### 5.1 GPU环境要求

**必需组件:**
- NVIDIA GPU(计算能力 >= 6.0)
- NVIDIA Driver >= 470.x
- nvidia-docker2 或 nvidia-container-toolkit

**验证GPU可用性:**

```bash
# 检查GPU设备
ls -l /dev/nvidia*

# 检查驱动版本
cat /proc/driver/nvidia/version

# Docker运行时测试 (使用CUDA 11.8匹配编译环境)
docker run --rm --runtime=nvidia nvidia/cuda:11.8.0-runtime-ubuntu22.04 nvidia-smi
```

### 5.2 GPU检测日志

**GPU可用时:**

```
[capability] Initializing ONNXRuntime session...
[capability] GPU mode enabled
[capability] desktop_recapture_detect initialized successfully
```

**GPU不可用时(自动回退CPU):**

```
[capability] Initializing ONNXRuntime session...
[capability] CUDA unavailable, using CPU
[capability] desktop_recapture_detect initialized successfully
```

### 5.3 性能对比

| 执行模式 | 推理时间 | 性能提升 |
|---------|---------|---------|
| GPU (CUDA + cuDNN) | 10-50ms | 基准 |
| CPU (多线程) | 50-150ms | 慢 3-10倍 |

---

## 6. 热重载机制

### 6.1 热重载原理

热重载通过以下步骤实现:

1. **调用热重载API** - HTTP POST请求触发
2. **Runtime重新加载能力** - C++ Runtime调用AiReload
3. **保持实例池** - 旧实例逐步释放,新请求使用新实例
4. **无服务中断** - 正在执行的推理不受影响

### 6.2 热重载API

**全部能力热重载:**

```bash
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"

# 响应:
# {
#   "reloaded": ["desktop_recapture_detect", "face_detect"],
#   "failed": []
# }
```

**单个能力热重载:**

```bash
curl -X POST http://localhost:8080/api/v1/admin/reload/desktop_recapture_detect \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"

# 响应:
# {
#   "reloaded": "desktop_recapture_detect",
#   "version": "1.0.0"
# }
```

### 6.3 适用场景

- **模型版本更新** - 修改current符号链接指向新版本后热重载
- **SO库更新** - 替换SO文件后热重载
- **配置参数调整** - 修改preprocess.json等配置后热重载

---

## 7. 验证与测试

### 7.1 端到端测试清单

#### ✅ 部署验证

```bash
# 1. 检查容器运行状态
docker ps | grep ai-prod

# 2. 检查日志无错误
docker logs ai-prod --tail 100

# 3. 检查GPU检测
docker logs ai-prod | grep "GPU mode enabled"

# 4. 检查能力加载
curl http://localhost:8080/api/v1/health | jq '.capabilities'
```

#### ✅ 推理功能验证

```bash
# 测试desktop_recapture_detect推理
curl -X POST http://localhost:8080/api/v1/infer/desktop_recapture_detect \
  -F "image=@test_desktop.jpg" \
  -o result.json

# 检查返回结果
cat result.json | jq .
# 应包含:
# {
#   "code": 0,
#   "message": "success",
#   "capability": "desktop_recapture_detect",
#   "model_version": "1.0.0",
#   "inference_time_ms": 25.6,
#   "result": {
#     "is_recapture": false,
#     "confidence": 0.98
#   }
# }
```

#### ✅ 授权验证

```bash
# 1. 有效授权 - 应成功
curl -X POST http://localhost:8080/api/v1/infer/desktop_recapture_detect \
  -F "image=@test.jpg"

# 2. 未授权能力 - 应返回403
curl -X POST http://localhost:8080/api/v1/infer/unauthorized_capability \
  -F "image=@test.jpg"
# 预期响应: {"code": 4004, "message": "Capability not licensed"}

# 3. 过期授权 - 应返回403
# (需要修改license.bin的valid_until字段为过去时间测试)
```

#### ✅ 性能测试

```bash
# 并发压测(使用ab工具)
ab -n 1000 -c 10 -p test_request.json \
   -T "application/json" \
   http://localhost:8080/api/v1/infer/desktop_recapture_detect

# 预期:
# GPU模式: 平均响应时间 < 50ms, QPS > 200
# CPU模式: 平均响应时间 < 150ms, QPS > 70
```

### 7.2 问题排查

**SO库加载失败:**

```bash
# 检查SO库路径
ls -l /mnt/ai_platform/libs/linux_x86_64/*/lib/*.so

# 检查符号链接
readlink -f /mnt/ai_platform/libs/linux_x86_64/desktop_recapture_detect/lib/libdesktop_recapture_detect.so

# 检查动态库依赖
ldd /mnt/ai_platform/libs/linux_x86_64/desktop_recapture_detect/lib/libdesktop_recapture_detect.so.1.0.0
```

**模型加载失败:**

```bash
# 检查manifest.json是否存在
ls -l /mnt/ai_platform/models/desktop_recapture_detect/current/manifest.json

# 检查model.onnx是否存在
ls -l /mnt/ai_platform/models/desktop_recapture_detect/current/model.onnx

# 检查current符号链接
readlink -f /mnt/ai_platform/models/desktop_recapture_detect/current
```

---

## 8. 常见问题FAQ

### Q1: 新增能力后是否需要重启容器?

**A:** 不需要。使用热重载API即可:

```bash
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"
```

只有以下情况需要重启容器:
- 修改了环境变量
- 更换了基础镜像
- Docker挂载配置变更

### Q2: 如何回滚到旧版本模型?

**A:** 修改current符号链接,然后热重载:

```bash
# 切换到旧版本
cd /data/ai_platform/models/desktop_recapture_detect
rm current
ln -s v0.9.0 current

# 触发热重载
curl -X POST http://localhost:8080/api/v1/admin/reload/desktop_recapture_detect \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"
```

### Q3: GPU不可用时推理是否正常?

**A:** 完全正常。C++ SO在初始化时会自动检测GPU,如果GPU不可用会自动回退到CPU推理。功能完全一致,仅性能降低3-10倍。

### Q4: 多个能力可以共享一个libai_runtime.so吗?

**A:** 可以。ai-builder编译时会为每个能力输出一份libai_runtime.so,但它们是相同的。Runtime在初始化时会自动发现任意一个能力目录下的libai_runtime.so并加载。

### Q5: 如何验证SO库是GPU版本还是CPU版本?

**A:** 检查动态库依赖:

```bash
ldd /mnt/ai_platform/libs/linux_x86_64/desktop_recapture_detect/lib/libdesktop_recapture_detect.so | grep cuda

# GPU版本会显示:
# libcudart.so.12 => /usr/local/cuda/lib64/libcudart.so.12
# libcudnn.so.8 => /usr/lib/x86_64-linux-gnu/libcudnn.so.8

# CPU版本不会有cuda相关依赖
```

### Q6: 授权文件如何添加新能力?

**A:** 在授权管理Web界面重新生成License,或使用授权API:

```bash
# 调用授权API添加新能力
curl -X POST http://localhost:8081/api/v1/licenses \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "customer_001",
    "capabilities": ["desktop_recapture_detect", "face_detect", "new_capability"],
    "valid_until": "2027-12-31T23:59:59+08:00"
  }'

# 下载生成的license.bin并替换宿主机文件
cp new_license.bin /data/ai_platform/licenses/license.bin

# 无需重启,Runtime会定期重新读取license
```

### Q7: 如何监控GPU使用率?

**A:** 使用nvidia-smi或容器内监控:

```bash
# 宿主机查看
nvidia-smi -l 1

# 容器内查看
docker exec ai-prod nvidia-smi

# 集成监控(Prometheus + Grafana)
# 使用NVIDIA DCGM Exporter采集GPU指标
```

### Q8: 生产镜像是否支持ARM架构?

**A:** 支持。需要编译ARM版本SO库,生产镜像本身仍使用ubuntu:22.04基础镜像:

```bash
# ARM64生产镜像 (与x86_64使用相同基础镜像)
# GPU支持由SO库内部实现,不依赖CUDA基础镜像
# 如需GPU加速,需在ARM主机上安装NVIDIA驱动和nvidia-docker
```

挂载目录结构:

```
/data/ai_platform/libs/linux_aarch64/desktop_recapture_detect/lib/
```

---

## 9. 最佳实践

### 9.1 生产部署建议

1. **版本化管理** - 模型和SO库使用版本目录,通过符号链接切换
2. **备份旧版本** - 回滚前保留至少1个历史版本
3. **分阶段发布** - 先在测试环境验证,再部署生产
4. **监控告警** - 集成Prometheus/Grafana监控推理延迟、GPU使用率
5. **日志收集** - 配置ELK或Loki收集推理日志

### 9.2 性能调优

1. **实例池大小** - 根据并发需求调整每个能力的实例数(默认2个)
2. **GPU显存管理** - 多能力共享GPU时设置显存限制
3. **批处理推理** - 高吞吐场景使用批处理API(待实现)
4. **模型优化** - 使用onnxslim压缩模型,TensorRT加速

### 9.3 安全建议

1. **授权文件加密** - license.bin使用RSA-2048签名,防篡改
2. **公钥指纹验证** - 设置TRUSTED_PUBKEY_SHA256环境变量防公钥伪造
3. **网络隔离** - 生产容器仅暴露推理端口8080
4. **最小权限** - 挂载目录设置只读权限(SO库和模型为:ro)

---

**文档维护者:** Claude Sonnet 4.5
**最后更新:** 2026-04-02
**版权:** Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). All rights reserved.
