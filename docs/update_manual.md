# 更新手册

> **北京爱知之星科技股份有限公司 (Agile Star)**
>
> AI 平台生产环境更新操作指南

---

## 目录

1. [模型更新](#1-模型更新)
2. [SO 插件更新](#2-so-插件更新)
3. [License 更新](#3-license-更新)
4. [Pipeline 配置更新](#4-pipeline-配置更新)
5. [服务镜像更新](#5-服务镜像更新)
6. [回滚操作](#6-回滚操作)
7. [注意事项](#7-注意事项)

---

## 平台架构概览

| 组件 | 说明 |
|------|------|
| 容器名称 | `ai-prod` |
| 服务端口 | `8080` |
| Compose 文件 | `deploy/docker-compose.prod.yml` |
| 宿主机数据根目录 | `/data/ai_platform/` |

宿主机挂载目录结构：

```
/data/ai_platform/
├── models/<capability>/current/    # 模型文件（ONNX + manifest.json）
├── libs/linux_x86_64/<capability>/current/  # SO 插件
├── licenses/                       # license.bin + pubkey.pem
└── pipelines/                      # Pipeline JSON 配置
```

热加载接口：

```
POST /api/v1/admin/reload
Header: Authorization: Bearer <AI_ADMIN_TOKEN>
```

---

## 1. 模型更新

模型文件存放于 `/data/ai_platform/models/<capability>/` 下，通过 `current` 符号链接指向当前生效的版本目录。更新模型后可通过热加载接口使新模型生效，**无需重启容器**。

### 操作步骤

```bash
# 变量定义
CAPABILITY="face_detect"          # 替换为实际能力名称
NEW_VERSION="v2.1.0"
MODEL_BASE="/data/ai_platform/models/${CAPABILITY}"

# 1) 将新模型文件复制到版本目录
sudo mkdir -p "${MODEL_BASE}/${NEW_VERSION}"
sudo cp model.onnx manifest.json "${MODEL_BASE}/${NEW_VERSION}/"

# 2) 更新 current 符号链接
cd "${MODEL_BASE}"
sudo rm -f current
sudo ln -s "${NEW_VERSION}" current

# 3) 验证符号链接指向
ls -la current

# 4) 热加载，使新模型生效
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${AI_ADMIN_TOKEN}"
```

### 验证

- 热加载接口应返回成功状态码（`200`）。
- 查看容器日志确认模型已重新加载：

```bash
docker logs --tail 50 ai-prod
```

---

## 2. SO 插件更新

SO 插件存放于 `/data/ai_platform/libs/linux_x86_64/<capability>/` 下，同样通过 `current` 符号链接管理版本。由于 SO 库在进程启动时加载到内存，**更新后需要重启容器**才能生效。

### 操作步骤

```bash
# 变量定义
CAPABILITY="face_detect"
NEW_VERSION="v1.3.0"
LIB_BASE="/data/ai_platform/libs/linux_x86_64/${CAPABILITY}"

# 1) 将新 SO 文件复制到版本目录
sudo mkdir -p "${LIB_BASE}/${NEW_VERSION}"
sudo cp lib${CAPABILITY}.so "${LIB_BASE}/${NEW_VERSION}/"

# 2) 更新 current 符号链接
cd "${LIB_BASE}"
sudo rm -f current
sudo ln -s "${NEW_VERSION}" current

# 3) 验证符号链接指向
ls -la current

# 4) 重启容器使新 SO 生效
cd /path/to/project/deploy
docker compose -f docker-compose.prod.yml restart ai-prod
```

### 验证

```bash
# 确认容器已正常重启
docker ps --filter name=ai-prod

# 查看启动日志，确认 SO 加载无错误
docker logs --tail 50 ai-prod
```

---

## 3. License 更新

License 文件位于 `/data/ai_platform/licenses/` 目录，包含 `license.bin` 和 `pubkey.pem`。更新 license 后通过热加载接口生效，**无需重启容器**。

### 操作步骤

```bash
LICENSE_DIR="/data/ai_platform/licenses"

# 1) 备份当前 license
sudo cp "${LICENSE_DIR}/license.bin" "${LICENSE_DIR}/license.bin.bak.$(date +%Y%m%d%H%M%S)"

# 2) 替换新的 license 文件
sudo cp new_license.bin "${LICENSE_DIR}/license.bin"

# 3) 如果公钥也需要更新
sudo cp new_pubkey.pem "${LICENSE_DIR}/pubkey.pem"

# 4) 热加载使新 license 生效
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${AI_ADMIN_TOKEN}"
```

### 验证

- 热加载接口返回 `200`。
- 查看日志确认 license 验证通过：

```bash
docker logs --tail 50 ai-prod | grep -i license
```

---

## 4. Pipeline 配置更新

Pipeline JSON 配置文件位于 `/data/ai_platform/pipelines/` 目录。可直接编辑或新增 JSON 文件，然后通过热加载接口生效。

### 操作步骤

```bash
PIPELINE_DIR="/data/ai_platform/pipelines"

# 1) 备份现有配置
sudo cp "${PIPELINE_DIR}/pipeline.json" \
        "${PIPELINE_DIR}/pipeline.json.bak.$(date +%Y%m%d%H%M%S)"

# 2) 编辑或替换配置文件
sudo vi "${PIPELINE_DIR}/pipeline.json"
# 或直接复制新配置文件
# sudo cp new_pipeline.json "${PIPELINE_DIR}/pipeline.json"

# 3) 验证 JSON 格式正确
python3 -m json.tool "${PIPELINE_DIR}/pipeline.json" > /dev/null

# 4) 热加载使配置生效
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${AI_ADMIN_TOKEN}"
```

### 验证

```bash
docker logs --tail 50 ai-prod | grep -i pipeline
```

---

## 5. 服务镜像更新

当服务本身发布了新版本镜像时，需要拉取新镜像并重建容器。

### 操作步骤

```bash
cd /path/to/project/deploy

# 1) 拉取最新镜像
docker compose -f docker-compose.prod.yml pull ai-prod

# 2) 停止并重建容器（数据卷挂载不受影响）
docker compose -f docker-compose.prod.yml up -d --force-recreate ai-prod

# 3) 清理旧镜像（可选）
docker image prune -f
```

### 验证

```bash
# 确认容器已使用新镜像运行
docker ps --filter name=ai-prod
docker inspect ai-prod --format='{{.Config.Image}}'

# 确认服务正常响应
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${AI_ADMIN_TOKEN}"

# 查看启动日志
docker logs --tail 100 ai-prod
```

---

## 6. 回滚操作

模型和 SO 插件均采用版本目录 + `current` 符号链接的管理方式，回滚只需将 `current` 重新指向上一版本即可。

### 6.1 模型回滚

```bash
CAPABILITY="face_detect"
PREV_VERSION="v2.0.0"
MODEL_BASE="/data/ai_platform/models/${CAPABILITY}"

# 查看可用版本
ls "${MODEL_BASE}"

# 回滚符号链接
cd "${MODEL_BASE}"
sudo rm -f current
sudo ln -s "${PREV_VERSION}" current

# 热加载
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${AI_ADMIN_TOKEN}"
```

### 6.2 SO 插件回滚

```bash
CAPABILITY="face_detect"
PREV_VERSION="v1.2.0"
LIB_BASE="/data/ai_platform/libs/linux_x86_64/${CAPABILITY}"

# 查看可用版本
ls "${LIB_BASE}"

# 回滚符号链接
cd "${LIB_BASE}"
sudo rm -f current
sudo ln -s "${PREV_VERSION}" current

# 重启容器
cd /path/to/project/deploy
docker compose -f docker-compose.prod.yml restart ai-prod
```

### 6.3 License 回滚

```bash
LICENSE_DIR="/data/ai_platform/licenses"

# 查看可用备份
ls "${LICENSE_DIR}"/license.bin.bak.*

# 恢复备份
sudo cp "${LICENSE_DIR}/license.bin.bak.<时间戳>" "${LICENSE_DIR}/license.bin"

# 热加载
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${AI_ADMIN_TOKEN}"
```

### 6.4 Pipeline 配置回滚

```bash
PIPELINE_DIR="/data/ai_platform/pipelines"

# 查看可用备份
ls "${PIPELINE_DIR}"/pipeline.json.bak.*

# 恢复备份
sudo cp "${PIPELINE_DIR}/pipeline.json.bak.<时间戳>" "${PIPELINE_DIR}/pipeline.json"

# 热加载
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer ${AI_ADMIN_TOKEN}"
```

### 6.5 服务镜像回滚

```bash
cd /path/to/project/deploy

# 在 docker-compose.prod.yml 中将镜像 tag 改回上一版本，然后重建
docker compose -f docker-compose.prod.yml up -d --force-recreate ai-prod
```

---

## 7. 注意事项

### 通用原则

1. **操作前务必备份**：更新任何文件前，先备份当前版本，确保可随时回滚。
2. **使用版本化目录**：模型和 SO 插件请始终创建带版本号的目录（如 `v2.1.0`），不要直接覆盖 `current` 目录中的文件。
3. **符号链接原子切换**：通过删除并重建 `current` 符号链接来切换版本，保证切换的原子性。

### 热加载 vs 重启

| 更新类型 | 生效方式 |
|----------|----------|
| 模型文件 | 热加载（`/api/v1/admin/reload`） |
| SO 插件 | **必须重启容器** |
| License | 热加载（`/api/v1/admin/reload`） |
| Pipeline 配置 | 热加载（`/api/v1/admin/reload`） |
| 服务镜像 | 重建容器 |

### 安全事项

- `AI_ADMIN_TOKEN` 为管理员令牌，请妥善保管，切勿泄露或写入版本控制。
- 所有热加载请求需通过 `Authorization: Bearer <AI_ADMIN_TOKEN>` 头部认证。
- 生产环境操作建议至少两人在场确认。

### Docker 相关

- 本项目使用 **`docker compose`**（v2，带空格），而非 `docker-compose`（v1）。
- Compose 文件路径：`deploy/docker-compose.prod.yml`。
- 重建容器时宿主机挂载的数据卷不受影响，无需担心数据丢失。

### 日志排查

如更新后出现异常，请首先检查容器日志：

```bash
# 查看最近日志
docker logs --tail 200 ai-prod

# 实时跟踪日志
docker logs -f ai-prod
```

### 网络与端口

- 服务默认监听 **8080** 端口，更新前后请确认端口未被占用。
- 如遇端口冲突，检查是否有旧容器未正确停止：

```bash
docker ps -a --filter name=ai-prod
```

---

> 如有任何疑问，请联系平台运维团队。
