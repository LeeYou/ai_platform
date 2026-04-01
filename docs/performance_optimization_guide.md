# 性能优化指南
# Performance Optimization Guide

本文档提供 AI 能力平台性能优化的最佳实践和调优建议。

---

## 目录

1. [推理性能优化](#推理性能优化)
2. [训练性能优化](#训练性能优化)
3. [Docker 容器优化](#docker-容器优化)
4. [网络和 I/O 优化](#网络和-io-优化)
5. [资源配置建议](#资源配置建议)
6. [监控和诊断](#监控和诊断)

---

## 推理性能优化

### 1. GPU 加速配置

**推荐配置**：
```bash
# docker-compose.prod.yml
services:
  prod:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      AI_BACKEND: onnxruntime-gpu
```

**性能提升**：GPU 推理速度可比 CPU 快 **10-50 倍**。

**验证 GPU 可用性**：
```bash
docker exec ai-prod nvidia-smi
docker exec ai-prod python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

### 2. TensorRT 加速

**适用场景**：NVIDIA GPU 部署，ONNX 模型优化。

**配置步骤**：
```bash
# 1. 安装 TensorRT execution provider
pip install onnxruntime-gpu==1.16.0

# 2. 转换 ONNX 模型为 TensorRT engine
trtexec --onnx=model.onnx \
        --saveEngine=model.trt \
        --fp16 \
        --workspace=4096

# 3. 在推理时使用 TensorRT provider
providers = ['TensorRTExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
session = ort.InferenceSession('model.onnx', providers=providers)
```

**性能提升**：在 NVIDIA GPU 上可额外提升 **2-5 倍**速度。

### 3. 模型量化

**INT8 量化**（推荐生产环境）：
```python
# export.py 中添加量化
import onnx
from onnxruntime.quantization import quantize_dynamic, QuantType

model_fp32 = 'model.onnx'
model_int8 = 'model_int8.onnx'

quantize_dynamic(
    model_fp32,
    model_int8,
    weight_type=QuantType.QInt8
)
```

**性能对比**：
| 量化方式 | 模型大小 | 推理速度 | 精度损失 |
|---------|---------|---------|---------|
| FP32 (原始) | 100% | 1.0x | 0% |
| FP16 | 50% | 1.5-2x | <0.5% |
| INT8 | 25% | 2-4x | 1-3% |

### 4. 实例池配置优化

**默认配置**：
```bash
AI_MAX_INSTANCES=4  # 每个能力最多 4 个并发实例
```

**调优建议**：
```python
# 根据 GPU 显存计算最优实例数
# 公式：max_instances = GPU_MEMORY_GB / MODEL_MEMORY_GB - 1

# 示例：12GB GPU，模型占用 2GB
AI_MAX_INSTANCES=5  # (12 / 2) - 1 = 5

# 示例：24GB GPU，模型占用 1.5GB
AI_MAX_INSTANCES=15  # (24 / 1.5) - 1 = 15
```

**CPU 推理**：
```bash
# CPU 推理建议基于核心数
AI_MAX_INSTANCES=4  # 8 核 CPU → 4 实例
AI_MAX_INSTANCES=8  # 16 核 CPU → 8 实例
```

### 5. 批处理优化

**适用场景**：处理大量离线数据。

**实现方式**：
```python
# 修改推理引擎支持批处理
def infer_batch(self, images: list[np.ndarray], options: dict | None = None):
    # 批量预处理
    tensors = [self._preprocess(img) for img in images]
    batch_tensor = np.concatenate(tensors, axis=0)

    # 批量推理
    outputs = self._session.run(None, {self._input_name: batch_tensor})

    # 批量后处理
    results = []
    for i in range(len(images)):
        result = self._postprocess([o[i:i+1] for o in outputs], options or {})
        results.append(result)

    return results
```

**性能提升**：批处理可提升吞吐量 **2-3 倍**。

### 6. 图像预处理优化

**使用 OpenCV 硬件加速**：
```python
# 启用 OpenCV CUDA 加速
import cv2
cv2.setUseOptimized(True)
cv2.setNumThreads(4)

# 使用 resize 的快速插值
img = cv2.resize(img, (640, 640), interpolation=cv2.INTER_LINEAR)  # 快速
# 避免: cv2.INTER_CUBIC (慢但高质量)
```

**并行预处理**：
```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    preprocessed = list(executor.map(self._preprocess, images))
```

---

## 训练性能优化

### 1. 数据加载优化

**DataLoader 配置**：
```python
train_loader = DataLoader(
    dataset,
    batch_size=32,
    num_workers=8,          # 多进程加载
    pin_memory=True,        # 加速 GPU 传输
    prefetch_factor=2,      # 预取数据
    persistent_workers=True # 保持 worker 进程
)
```

**性能提升**：优化后数据加载不再是瓶颈（CPU 利用率 > 80%）。

### 2. 混合精度训练 (AMP)

**PyTorch 实现**：
```python
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

for images, labels in train_loader:
    optimizer.zero_grad()

    # 自动混合精度
    with autocast():
        outputs = model(images)
        loss = criterion(outputs, labels)

    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()
```

**性能提升**：训练速度提升 **50-100%**，显存占用减少 **30-50%**。

### 3. 梯度累积

**适用场景**：GPU 显存不足，无法使用大 batch size。

**实现**：
```python
accumulation_steps = 4  # 累积 4 个 mini-batch

for i, (images, labels) in enumerate(train_loader):
    outputs = model(images)
    loss = criterion(outputs, labels) / accumulation_steps

    loss.backward()

    if (i + 1) % accumulation_steps == 0:
        optimizer.step()
        optimizer.zero_grad()
```

**等效 batch size**：`effective_batch_size = batch_size × accumulation_steps`

### 4. 分布式训练 (DDP)

**PyTorch DistributedDataParallel**：
```python
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP

# 初始化进程组
dist.init_process_group(backend='nccl')

# 包装模型
model = DDP(model, device_ids=[local_rank])

# 使用 DistributedSampler
train_sampler = DistributedSampler(dataset)
train_loader = DataLoader(dataset, sampler=train_sampler, ...)

# 训练循环
for epoch in range(epochs):
    train_sampler.set_epoch(epoch)  # 重要：确保每个 epoch 数据不同
    for batch in train_loader:
        ...
```

**性能提升**：2 卡 GPU 训练速度提升 **1.8-1.9 倍**，4 卡提升 **3.5-3.8 倍**。

### 5. 编译优化 (torch.compile)

**PyTorch 2.0+ 特性**：
```python
import torch

# 编译模型（首次运行会慢，后续快速）
model = torch.compile(model, mode='reduce-overhead')

# 训练
for images, labels in train_loader:
    outputs = model(images)  # 使用优化后的计算图
    ...
```

**性能提升**：训练速度提升 **10-30%**（取决于模型架构）。

---

## Docker 容器优化

### 1. 共享内存配置

**问题现象**：DataLoader 多进程加载时报错。

**解决方案**：
```yaml
# docker-compose.yml
services:
  train:
    shm_size: '4gb'  # 增加共享内存（默认 64MB）
```

**推荐值**：
- 训练容器：4-8GB
- 推理容器：1-2GB

### 2. 资源限制

**合理配置资源上限**：
```yaml
services:
  prod:
    deploy:
      resources:
        limits:
          cpus: '8.0'      # CPU 核心数
          memory: 16G      # 内存上限
        reservations:
          memory: 8G       # 保留内存
```

**推荐配置**：
| 服务 | CPU | 内存 | GPU |
|-----|-----|------|-----|
| train | 8-16 | 16-32G | 1 |
| test | 4-8 | 8-16G | 0-1 |
| prod | 4-8 | 8-16G | 1 |
| license | 2-4 | 2-4G | 0 |

### 3. 日志轮转

**当前配置**：
```python
handler = RotatingFileHandler(
    "prod.log",
    maxBytes=50 * 1024 * 1024,  # 50MB
    backupCount=10               # 保留 10 个历史文件
)
```

**优化建议**：
- 高负载场景：`maxBytes=100MB, backupCount=5`
- 低负载场景：`maxBytes=20MB, backupCount=3`

---

## 网络和 I/O 优化

### 1. 文件系统选择

**性能对比**：
| 文件系统 | 顺序读 | 随机读 | 小文件 | 推荐用途 |
|---------|--------|--------|--------|---------|
| ext4 | 良好 | 中等 | 中等 | 通用 |
| XFS | 优秀 | 良好 | 良好 | 大文件（模型、数据集） |
| Btrfs | 良好 | 中等 | 差 | 需要快照功能 |
| NFS | 差 | 差 | 差 | 不推荐用于训练 |

**推荐配置**：
```bash
# 使用 XFS 挂载数据目录
mkfs.xfs /dev/sdb1
mount -o noatime,nodiratime /dev/sdb1 /data/ai_platform
```

### 2. 数据集缓存

**使用 tmpfs 缓存热数据**：
```yaml
services:
  train:
    volumes:
      - type: tmpfs
        target: /tmp/dataset_cache
        tmpfs:
          size: 10G  # RAM 缓存 10GB
```

**Python 实现**：
```python
import shutil

# 训练前复制数据集到内存
shutil.copytree('/workspace/datasets/face_detect/', '/tmp/dataset_cache/')

# 使用缓存路径训练
dataset = FaceDataset('/tmp/dataset_cache/')
```

**性能提升**：数据加载速度提升 **5-10 倍**（RAM vs SSD）。

### 3. HTTP 连接池

**FastAPI 客户端优化**：
```python
import httpx

# 使用连接池
async with httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
) as client:
    response = await client.post(...)
```

---

## 资源配置建议

### 生产环境推荐配置

**小规模部署（<100 QPS）**：
```
服务器：16 核 CPU，64GB RAM，NVIDIA RTX 4090 (24GB)
容器配置：
  - prod: 8 核，16GB，1 GPU
  - AI_MAX_INSTANCES: 10
  - UVICORN_WORKERS: 2
```

**中规模部署（100-500 QPS）**：
```
服务器：32 核 CPU，128GB RAM，NVIDIA A100 (40GB) × 2
容器配置：
  - prod: 16 核，32GB，2 GPU
  - AI_MAX_INSTANCES: 20
  - UVICORN_WORKERS: 4
负载均衡：Nginx + 2-3 个 prod 容器
```

**大规模部署（>500 QPS）**：
```
Kubernetes 集群：3+ 节点
每节点：32 核 CPU，256GB RAM，NVIDIA A100 (80GB) × 4
HPA 配置：根据 CPU/内存/GPU 使用率自动扩缩容
服务网格：Istio 进行流量管理和 A/B 测试
```

---

## 监控和诊断

### 1. 性能分析工具

**Python 性能分析**：
```bash
# 使用 cProfile
python -m cProfile -o profile.stats train.py

# 分析结果
python -m pstats profile.stats
> sort cumtime
> stats 20

# 或使用可视化工具
pip install snakeviz
snakeviz profile.stats
```

**PyTorch Profiler**：
```python
from torch.profiler import profile, ProfilerActivity

with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
    for _ in range(10):
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()

print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=10))
```

### 2. GPU 监控

**实时监控**：
```bash
# nvidia-smi 实时刷新
watch -n 1 nvidia-smi

# 或使用 dmon 模式
nvidia-smi dmon -s ucm -c 100

# 监控指标：
# - GPU 利用率 (应 > 80%)
# - 显存使用 (应 < 90%)
# - 温度 (应 < 85°C)
```

**长期监控**：
```bash
# 使用 Prometheus + Grafana
# 安装 NVIDIA GPU Exporter
docker run -d --gpus all \
  -p 9445:9445 \
  nvidia/dcgm-exporter:latest
```

### 3. 推理性能基准测试

**创建基准测试脚本**：
```python
import time
import numpy as np

def benchmark_inference(model, input_shape=(1, 3, 640, 640), iterations=100):
    """Benchmark inference performance."""
    dummy_input = np.random.randn(*input_shape).astype(np.float32)

    # Warmup
    for _ in range(10):
        _ = model.infer(dummy_input)

    # Benchmark
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        _ = model.infer(dummy_input)
        times.append((time.perf_counter() - t0) * 1000)

    times = np.array(times)
    print(f"Inference Time Statistics:")
    print(f"  Mean:   {times.mean():.2f} ms")
    print(f"  Median: {np.median(times):.2f} ms")
    print(f"  P95:    {np.percentile(times, 95):.2f} ms")
    print(f"  P99:    {np.percentile(times, 99):.2f} ms")
    print(f"  Min:    {times.min():.2f} ms")
    print(f"  Max:    {times.max():.2f} ms")

# 使用
benchmark_inference(engine)
```

### 4. 性能剖析报告

**详细性能数据（新增功能）**：
```python
# 推理返回的性能数据
{
  "result": {...},
  "infer_time_ms": 25.4,
  "performance": {
    "preprocess_ms": 3.2,    # 图像预处理耗时
    "inference_ms": 18.5,    # 模型推理耗时
    "postprocess_ms": 3.7    # 后处理耗时
  }
}
```

**性能优化目标**：
| 阶段 | 占比目标 | 优化方向 |
|-----|---------|---------|
| Preprocess | <15% | 优化图像 resize、归一化 |
| Inference | 70-80% | 模型量化、TensorRT |
| Postprocess | <15% | 优化 NMS、结果解析 |

---

## 性能优化检查清单

**推理优化**：
- [ ] 启用 GPU 推理 (onnxruntime-gpu)
- [ ] 配置 TensorRT execution provider
- [ ] 使用 INT8/FP16 量化模型
- [ ] 调优实例池大小 (AI_MAX_INSTANCES)
- [ ] 启用批处理（离线场景）
- [ ] 优化图像预处理（OpenCV 加速）

**训练优化**：
- [ ] 混合精度训练 (AMP)
- [ ] 优化 DataLoader (num_workers, pin_memory)
- [ ] 梯度累积（显存不足时）
- [ ] 分布式训练（多 GPU）
- [ ] torch.compile 编译优化
- [ ] 数据集缓存到 tmpfs

**系统优化**：
- [ ] 增加 Docker 共享内存 (shm_size)
- [ ] 配置合理的资源限制
- [ ] 使用 XFS 文件系统
- [ ] 日志轮转配置
- [ ] GPU 温度和功耗监控

**网络优化**：
- [ ] HTTP 连接池配置
- [ ] Nginx 负载均衡（多实例）
- [ ] CDN 缓存静态资源
- [ ] 压缩响应数据 (gzip)

---

**最后更新**: 2026-03-31
**版本**: v1.0
