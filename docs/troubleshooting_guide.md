# 故障排查指南
# Troubleshooting Guide

本文档提供 AI 能力平台常见问题的诊断和解决方案。

---

## 目录

1. [Docker 构建问题](#docker-构建问题)
2. [训练子系统问题](#训练子系统问题)
3. [测试子系统问题](#测试子系统问题)
4. [授权子系统问题](#授权子系统问题)
5. [编译子系统问题](#编译子系统问题)
6. [生产推理问题](#生产推理问题)
7. [性能问题](#性能问题)
8. [网络和连接问题](#网络和连接问题)

---

## Docker 构建问题

### 问题 1: Docker 构建过程中包重复下载

**现象**：
```
Step 15/25 : RUN pip install --no-cache-dir -r requirements.txt
 ---> Running in abc123
Collecting torch==2.0.1...
Downloading torch-2.0.1-cp311...
```
每次构建都重新下载 PyTorch 等大包。

**原因**：
- 源代码改动导致 Docker 层缓存失效
- requirements.txt 在源代码之后被复制

**解决方案**：
1. 确保 Dockerfile 中 `COPY requirements.txt` 在 `COPY source/` 之前
2. 使用国内镜像源加速下载（已在最新 Dockerfile 中配置）

```dockerfile
# ✅ 正确顺序
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ src/

# ❌ 错误顺序
COPY src/ src/
COPY requirements.txt .
RUN pip install -r requirements.txt
```

### 问题 2: CUDA OOM (Out of Memory) 错误

**现象**：
```
RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB
```

**原因**：
- GPU 显存不足
- batch_size 设置过大
- 多个训练任务同时运行

**解决方案**：
```bash
# 1. 查看 GPU 使用情况
nvidia-smi

# 2. 减小 batch_size
# 在训练配置 JSON 中设置：
{
  "batch_size": 8  # 从 32 降低到 8
}

# 3. 停止其他训练任务
docker exec ai-train pkill -f train.py

# 4. 清理 GPU 缓存（重启容器）
docker restart ai-train
```

### 问题 3: npm install 失败或速度慢

**现象**：
```
npm ERR! network timeout at https://registry.npmjs.org/...
```

**解决方案**：
```bash
# 已在 Dockerfile 中配置淘宝镜像源
# 手动设置（如果需要）：
npm config set registry https://registry.npmmirror.com

# 清除缓存后重试：
npm cache clean --force
npm install
```

---

## 训练子系统问题

### 问题 4: 训练任务无法启动

**现象**：
Web UI 中创建训练任务后，状态一直为 "pending"。

**诊断步骤**：
```bash
# 1. 检查 Celery worker 是否运行
docker exec ai-train ps aux | grep celery

# 2. 查看 Celery 日志
docker logs ai-train | grep -i celery

# 3. 检查 Redis 连接
docker exec ai-train redis-cli -h redis ping
```

**常见原因和解决方案**：

**原因 A**: Celery worker 未启动
```bash
# 解决：重启训练容器
docker restart ai-train

# 或手动启动 worker
docker exec -d ai-train celery -A tasks worker --loglevel=info
```

**原因 B**: Redis 连接失败
```bash
# 检查 Redis 容器
docker ps | grep redis

# 检查网络连接
docker network inspect ai_platform_default
```

### 问题 5: 训练过程中断或失败

**现象**：
训练日志显示错误或训练进度停止更新。

**诊断步骤**：
```bash
# 1. 查看训练日志
docker exec ai-train tail -f /workspace/logs/train_{job_id}.log

# 2. 检查数据集路径
docker exec ai-train ls -la /workspace/datasets/{capability}/

# 3. 检查磁盘空间
docker exec ai-train df -h
```

**常见错误**：

**错误 A**: `FileNotFoundError: dataset.yaml not found`
```bash
# 解决：确认数据集目录结构
/workspace/datasets/face_detect/
├── images/
│   ├── train/
│   └── val/
└── dataset.yaml
```

**错误 B**: `RuntimeError: DataLoader worker (pid XXXX) exited unexpectedly`
```bash
# 解决：减少 num_workers 或增加共享内存
# 在 docker-compose.yml 中添加：
services:
  train:
    shm_size: '4gb'  # 增加共享内存
```

### 问题 6: ONNX 导出失败

**现象**：
```
torch.onnx.export() failed: AttributeError: 'Tensor' object has no attribute 'clone'
```

**解决方案**：
```bash
# 1. 确认 PyTorch 和 ONNX 版本兼容
pip list | grep -E 'torch|onnx'

# 2. 使用 opset_version 参数
# 在 export.py 中：
torch.onnx.export(
    model, dummy_input, "model.onnx",
    opset_version=13,  # 尝试不同版本: 11, 12, 13
    dynamic_axes={'input': {0: 'batch'}}
)

# 3. 简化模型（移除不支持的操作）
```

---

## 测试子系统问题

### 问题 7: ONNXRuntime 推理失败

**现象**：
```
onnxruntime.capi.onnxruntime_pybind11_state.Fail: [ONNXRuntimeError]
```

**诊断步骤**：
```bash
# 1. 验证 ONNX 模型有效性
python -c "import onnx; onnx.checker.check_model('model.onnx')"

# 2. 检查输入形状
python -c "
import onnxruntime as ort
sess = ort.InferenceSession('model.onnx')
print([i.shape for i in sess.get_inputs()])
"

# 3. 检查 ONNXRuntime 后端
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

**解决方案**：

**方案 A**: 输入形状不匹配
```python
# 在 preprocess.json 中确认尺寸：
{
  "resize": {"width": 640, "height": 640}
}

# 确保图片预处理后形状正确 (1, 3, 640, 640)
```

**方案 B**: CUDA provider 不可用
```bash
# 安装 GPU 版本 ONNXRuntime
pip uninstall onnxruntime
pip install onnxruntime-gpu==1.16.0

# 或使用 CPU provider
export AI_BACKEND=onnxruntime-cpu
```

### 问题 8: 批量评估速度慢

**现象**：
1000 张图片评估需要 30 分钟以上。

**优化方案**：
```python
# 1. 启用 GPU 推理
export AI_BACKEND=onnxruntime-gpu

# 2. 调整 batch processing
# 在测试代码中批量处理：
for batch in DataLoader(dataset, batch_size=16):
    results = model.infer(batch)

# 3. 使用 TensorRT (if available)
providers = ['TensorRTExecutionProvider', 'CUDAExecutionProvider']
sess = ort.InferenceSession('model.onnx', providers=providers)
```

---

## 授权子系统问题

### 问题 9: License 验证失败

**现象**：
```
ERROR | License verification FAILED — signature invalid
```

**诊断步骤**：
```bash
# 1. 检查 license.bin 存在
ls -l /data/ai_platform/licenses/license.bin

# 2. 检查 pubkey.pem 存在
ls -l /data/ai_platform/licenses/pubkey.pem

# 3. 查看 license 内容
cat /data/ai_platform/licenses/license.bin | jq .

# 4. 检查 pubkey 指纹
sha256sum /data/ai_platform/licenses/pubkey.pem
```

**常见错误**：

**错误 A**: 公钥和私钥不匹配
```bash
# 确认公钥与签名 license 的私钥匹配
# 重新生成 license 或更换正确的 pubkey.pem
```

**错误 B**: License 已过期
```bash
# 查看有效期
cat license.bin | jq '.valid_until'

# 联系管理员延期或重新签发
```

**错误 C**: 机器指纹不匹配
```bash
# 生成当前机器指纹
docker exec ai-license python tools/fingerprint.py

# 与 license 中的指纹对比
cat license.bin | jq '.machine_fingerprint'

# 如果不匹配，需重新签发 license
```

### 问题 10: License 过期后服务行为

**现象**：
健康检查正常但推理返回 4002 错误。

**预期行为**：
- `/api/v1/health` 仍然返回 200（允许监控系统检测）
- `/api/v1/infer/*` 返回 4002 `{"error": "License expired"}`

**解决方案**：
```bash
# 更新 license.bin 文件
cp new_license.bin /data/ai_platform/licenses/license.bin

# 热重载（无需重启）
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${AI_ADMIN_TOKEN}"
```

---

## 编译子系统问题

### 问题 11: CMake 配置失败

**现象**：
```
CMake Error: Could not find a package configuration file provided by "onnxruntime"
```

**解决方案**：
```bash
# 1. 确认构建环境有 ONNXRuntime 开发包
docker exec ai-builder-linux-x86 ls /usr/local/include/onnxruntime_c_api.h

# 2. 手动指定路径
cmake -B build -S . \
  -Donnxruntime_DIR=/usr/local/lib/cmake/onnxruntime

# 3. 或使用环境变量
export onnxruntime_DIR=/usr/local/lib/cmake/onnxruntime
cmake -B build -S .
```

### 问题 12: 编译出的 SO 文件无法加载

**现象**：
```
OSError: /lib/libai_face_detect.so: undefined symbol: OrtCreateEnv
```

**原因**：
链接 ONNXRuntime 库失败。

**解决方案**：
```cmake
# 在 CMakeLists.txt 中确认链接库：
target_link_libraries(face_detect
  PRIVATE
    onnxruntime
    ${CMAKE_DL_LIBS}
)

# 检查链接依赖
ldd /data/ai_platform/libs/linux_x86_64/face_detect/v1.0.0/libface_detect.so
```

### 问题 13: Windows DLL 编译失败

**现象**：
MSVC 编译器报错。

**诊断步骤**：
```bash
# 1. 确认 Windows builder 镜像构建成功
docker images | grep ai-builder-windows

# 2. 进入 builder 容器检查工具链
docker exec ai-builder-windows cmd /c "cl.exe /?"

# 3. 查看编译日志
docker logs ai-builder-windows | tail -100
```

**常见问题**：
- 缺少 Visual Studio 2022 Build Tools
- 缺少 Windows SDK
- 路径中包含中文或空格

---

## 生产推理问题

### 问题 14: 推理请求超时或 503 错误

**现象**：
```
HTTP 503 Service Unavailable
{"error": "Instance pool exhausted"}
```

**原因**：
所有推理实例繁忙，instance pool 耗尽。

**诊断步骤**：
```bash
# 1. 查看当前负载
curl http://localhost:8080/api/v1/health

# 2. 查看实例池配置
echo $AI_MAX_INSTANCES  # 默认 4

# 3. 查看容器资源使用
docker stats ai-prod
```

**解决方案**：
```bash
# 方案 A: 增加实例池大小
# 在 docker-compose.prod.yml 中：
environment:
  AI_MAX_INSTANCES: 8  # 从 4 增加到 8

# 方案 B: 增加容器资源限制
services:
  prod:
    deploy:
      resources:
        limits:
          memory: 8G  # 增加内存
          cpus: '4.0'  # 增加 CPU

# 方案 C: 添加负载均衡
# 部署多个 prod 容器 + Nginx 反向代理
```

### 问题 15: 模型 checksum 验证失败

**现象**（新增检查后）：
```
RuntimeError: Model checksum MISMATCH — possible corruption/tampering!
  Expected: abc123...
  Actual:   def456...
```

**原因**：
- 模型文件在传输过程中损坏
- 模型文件被意外修改
- checksum.sha256 文件与模型不匹配

**解决方案**：
```bash
# 1. 重新生成 checksum
sha256sum model.onnx > checksum.sha256

# 2. 或重新部署完整的模型包
rsync -av source/model_v1.0.0/ /data/ai_platform/models/face_detect/v1.0.0/

# 3. 验证文件完整性
sha256sum -c checksum.sha256
```

### 问题 16: 热重载失败

**现象**：
```
POST /api/v1/admin/reload returns 500
{"error": "Reload failed: manifest.json not found"}
```

**诊断步骤**：
```bash
# 1. 检查新模型包结构
ls -la /data/ai_platform/models/face_detect/v1.1.0/
# 应包含: model.onnx, manifest.json, preprocess.json, checksum.sha256

# 2. 验证 manifest.json 有效
cat manifest.json | jq .

# 3. 检查文件权限
chmod 644 model.onnx manifest.json preprocess.json
```

**解决方案**：
```bash
# 确保模型包完整：
/data/ai_platform/models/face_detect/v1.1.0/
├── model.onnx
├── manifest.json
├── preprocess.json
├── labels.json (可选)
└── checksum.sha256 (推荐)

# 更新 current 符号链接
cd /data/ai_platform/models/face_detect
ln -snf v1.1.0 current

# 执行热重载
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer changeme"
```

---

## 性能问题

### 问题 17: 推理速度慢

**现象**：
单次推理耗时超过 500ms（预期 < 50ms）。

**性能分析步骤**：
```bash
# 1. 查看推理结果中的耗时
curl -X POST http://localhost:8080/api/v1/infer/face_detect \
  -F "image=@test.jpg" | jq '.infer_time_ms'

# 2. 查看 GPU 使用情况
nvidia-smi dmon -s u

# 3. 查看 CPU 使用情况
docker stats ai-prod
```

**优化方案**：

**方案 A**: 启用 GPU 推理
```bash
# 确认 GPU 可用
docker exec ai-prod nvidia-smi

# 设置环境变量
export AI_BACKEND=onnxruntime-gpu
```

**方案 B**: 使用 TensorRT 优化
```bash
# 转换 ONNX 模型为 TensorRT engine
trtexec --onnx=model.onnx --saveEngine=model.trt \
  --fp16  # 或 --int8 for INT8 量化
```

**方案 C**: 模型量化
```bash
# 导出时使用 FP16 量化
python export.py --quantize fp16

# 或使用 INT8 量化（需要校准数据）
python export.py --quantize int8 --calib_data ./calib/
```

### 问题 18: 内存占用过高

**现象**：
容器内存使用超过 8GB。

**诊断**：
```bash
# 查看内存使用
docker stats ai-prod --no-stream

# 查看进程内存
docker exec ai-prod ps aux --sort=-%mem | head -10
```

**优化方案**：
```bash
# 1. 减少实例池大小
AI_MAX_INSTANCES=2

# 2. 减少 Uvicorn workers
UVICORN_WORKERS=1

# 3. 启用模型共享（Python）
# 在 inference_engine.py 中共享 ONNX session
```

---

## 网络和连接问题

### 问题 19: 容器间网络不通

**现象**：
训练容器无法连接 Redis。

**诊断**：
```bash
# 1. 检查网络
docker network ls
docker network inspect ai_platform_default

# 2. 测试连通性
docker exec ai-train ping redis

# 3. 检查端口
docker exec redis netstat -tln | grep 6379
```

**解决方案**：
```bash
# 重建网络
docker compose down
docker compose up -d
```

### 问题 20: 外部无法访问服务

**现象**：
浏览器无法打开 http://localhost:8080

**诊断**：
```bash
# 1. 检查端口映射
docker ps | grep ai-prod

# 2. 检查防火墙
sudo ufw status
sudo iptables -L -n | grep 8080

# 3. 测试本地连接
curl http://localhost:8080/api/v1/health
```

**解决方案**：
```bash
# 打开防火墙端口
sudo ufw allow 8080/tcp

# 或修改 docker-compose.yml 端口映射
ports:
  - "0.0.0.0:8080:8080"  # 监听所有网卡
```

---

## 日志查看和调试

### 集中查看所有日志

```bash
# 训练子系统
docker logs -f ai-train --tail 100

# 测试子系统
docker logs -f ai-test --tail 100

# 生产子系统
docker logs -f ai-prod --tail 100

# 授权子系统
docker logs -f ai-license --tail 100

# Redis 日志
docker logs -f redis --tail 50
```

### 调整日志级别

```bash
# 在 docker-compose.yml 中设置：
environment:
  LOG_LEVEL: debug  # info (默认), debug, warning, error
```

### 日志文件位置

```
/data/ai_platform/logs/
├── train.log          # 训练后端日志
├── test.log           # 测试后端日志
├── prod.log           # 生产推理日志
├── license.log        # 授权服务日志
└── train_<job_id>.log # 每个训练任务的日志
```

---

## 紧急恢复步骤

### 完全重置平台

```bash
# 1. 停止所有容器
docker compose -f deploy/docker-compose.yml down
docker compose -f deploy/docker-compose.prod.yml down

# 2. 清理容器和镜像（可选）
docker system prune -a

# 3. 重建
docker compose -f deploy/docker-compose.yml up -d --build

# 4. 验证
curl http://localhost:8001/health  # 训练
curl http://localhost:8002/health  # 测试
curl http://localhost:8003/health  # 授权
```

### 数据备份

```bash
# 备份关键数据
tar -czf ai_platform_backup_$(date +%Y%m%d).tar.gz \
  /data/ai_platform/models/ \
  /data/ai_platform/datasets/ \
  /data/ai_platform/licenses/ \
  /data/ai_platform/libs/

# 恢复
tar -xzf ai_platform_backup_20260330.tar.gz -C /
```

---

## 获取帮助

### 收集诊断信息

提交 issue 前，请收集以下信息：

```bash
# 系统信息
uname -a
docker version
docker compose version

# 容器状态
docker ps -a

# 容器日志（最近 100 行）
docker logs ai-prod --tail 100 > prod.log 2>&1

# 资源使用
docker stats --no-stream > docker_stats.txt

# 网络配置
docker network inspect ai_platform_default > network.json
```

### 联系支持

- GitHub Issues: https://github.com/LeeYou/ai_platform/issues
- 文档: /docs/
- 邮箱: support@agilestar.cn

---

**最后更新**: 2026-03-31
**版本**: v1.0
