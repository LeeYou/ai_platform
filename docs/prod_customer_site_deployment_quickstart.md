# AI 平台生产镜像客户现场部署手册（版本 B：极简操作版）

**北京爱知之星科技股份有限公司 (Agile Star)**  
**适用对象：** 客户现场实施工程师、运维工程师  
**适用镜像：** `agilestar/ai-prod`  
**目标：** 用最少步骤完成生产镜像部署、启动与验收

---

## 1. 你将拿到什么

标准交付包建议包含以下内容：

```text
delivery_package/
├── images/
│   └── agilestar_ai_prod_latest.tar
├── compose/
│   └── docker-compose.prod.yml
├── licenses/
│   ├── license.bin
│   └── pubkey.pem
├── resources/
│   ├── libs/
│   ├── models/
│   └── pipelines/
└── docs/
    ├── prod_customer_site_deployment_manual.md
    └── prod_customer_site_deployment_quickstart.md
```

客户现场部署时，默认采用**完全离线导入镜像**的方式。

客户现场**不需要**也**不会**拿到项目源码仓库，因此现场操作只基于交付包进行。

离线部署最少需要：

- 镜像包：`agilestar_ai_prod_latest.tar`
- 启动文件：`docker-compose.prod.yml`
- 授权文件：`license.bin`、`pubkey.pem`
- 资源文件：`libs/`、`models/`（如未全部内置于镜像）

---

## 2. 最短部署路径

如果你只想最快部署，请直接按以下顺序执行：

1. 安装 Docker
2. 如有 GPU，安装 NVIDIA Container Toolkit
3. 手动创建 `/data/ai_platform`
4. 导入离线镜像
5. 拷贝授权、模型、动态库到宿主机目录
6. 创建 `.env`
7. 启动 `docker compose`
8. 用 `health`、`capabilities`、`license/status` 验证

---

## 3. 步骤 1：安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

重新登录后验证：

```bash
docker --version
docker compose version
```

---

## 4. 步骤 2：如果有 GPU，再安装 NVIDIA 容器运行时

先检查：

```bash
nvidia-smi
```

如果能正常显示 GPU 信息，再执行：

```bash
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

验证：

```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 nvidia-smi
```

如果客户现场没有 GPU，可直接跳过本节。

---

## 5. 步骤 3：初始化宿主机目录

推荐统一使用：

```text
/data/ai_platform
```

由于客户现场不提供项目源码，因此请直接手动创建目录：

```bash
sudo mkdir -p /data/ai_platform/{licenses,pipelines,models}
sudo mkdir -p /data/ai_platform/logs/prod
sudo mkdir -p /data/ai_platform/libs/linux_x86_64
sudo chmod 700 /data/ai_platform/licenses
sudo chmod -R 777 /data/ai_platform/logs
```

---

## 6. 步骤 4：导入离线镜像

```bash
docker load -i agilestar_ai_prod_latest.tar
```

验证镜像：

```bash
docker images | grep ai-prod
```

应看到类似输出：

```text
agilestar/ai-prod   latest   <image_id>
```

---

## 7. 步骤 5：拷贝客户资源

## 7.1 拷贝授权文件

将客户授权文件放到：

```text
/data/ai_platform/licenses/
```

目录结构应为：

```text
/data/ai_platform/licenses/
├── license.bin
└── pubkey.pem
```

## 7.2 拷贝模型文件

每个 capability 模型都要放到：

```text
/data/ai_platform/models/<capability>/current/
```

并保证 `current/` 下存在：

- `manifest.json`
- 该 capability 对应模型文件

示例：

```text
/data/ai_platform/models/agface_fake_photo/current/
/data/ai_platform/models/agface_face_property/current/
/data/ai_platform/models/agface_barehead/current/
```

## 7.3 拷贝动态库文件

Linux x86_64 推荐目录结构：

```text
/data/ai_platform/libs/linux_x86_64/<capability>/current/lib/lib<capability>.so
```

例如：

```text
/data/ai_platform/libs/linux_x86_64/agface_fake_photo/current/lib/libagface_fake_photo.so
/data/ai_platform/libs/linux_x86_64/agface_face_property/current/lib/libagface_face_property.so
/data/ai_platform/libs/linux_x86_64/agface_barehead/current/lib/libagface_barehead.so
/data/ai_platform/libs/linux_x86_64/desktop_recapture_detect/current/lib/libdesktop_recapture_detect.so
```

同时请确保 runtime 主库也已经随交付产物提供并放置正确。

## 7.4 拷贝 pipeline 文件（如有）

```text
/data/ai_platform/pipelines/
```

---

## 8. 步骤 6：准备部署目录

建议建立单独部署目录：

```bash
sudo mkdir -p /opt/ai_platform_deploy
```

将 `docker-compose.prod.yml` 放入：

```text
/opt/ai_platform_deploy/
```

说明：

- 该 `docker-compose.prod.yml` 应由交付包直接提供
- 客户现场无需从源码仓库复制任何文件

然后创建 `.env`：

```bash
cat > /opt/ai_platform_deploy/.env <<'EOF'
AI_ARCH=linux_x86_64
AI_ADMIN_TOKEN=please-change-this-to-a-strong-random-token
AI_MAX_INSTANCES=4
AI_ACQUIRE_TIMEOUT_S=30
AI_INFER_MAX_CONCURRENCY=16
AI_INFER_CONCURRENCY_TIMEOUT_SECONDS=30
AI_MAX_UPLOAD_BYTES=52428800
UVICORN_WORKERS=2
LOG_LEVEL=info
EOF
```

### 最少必须修改的参数

- `AI_ADMIN_TOKEN`

生产环境**禁止**使用默认弱口令。

---

## 9. 步骤 7：启动服务

进入部署目录：

```bash
cd /opt/ai_platform_deploy
```

启动：

```bash
docker compose -f docker-compose.prod.yml up -d
```

查看状态：

```bash
docker compose -f docker-compose.prod.yml ps
```

查看日志：

```bash
docker compose -f docker-compose.prod.yml logs -f prod
```

如果客户现场使用的 compose 文件名不是 `docker-compose.prod.yml`，请以交付包中实际文件名为准。

---

## 10. 步骤 8：部署后验收

## 10.1 检查容器是否启动

```bash
docker ps | grep ai-prod
```

## 10.2 健康检查

```bash
curl http://localhost:8080/api/v1/health
```

重点看：

- `status` 是否为 `healthy`
- `runtime_initialized` 是否为 `true`
- `loaded_capability_count` 是否大于 `0`

## 10.3 检查已加载能力

```bash
curl http://localhost:8080/api/v1/capabilities
```

重点看：

- 交付给客户的 capability 是否都已出现在返回中

## 10.4 检查授权状态

```bash
curl http://localhost:8080/api/v1/license/status
```

重点看：

- `valid` 是否为 `true`
- `status` 是否为 `valid`

说明：

- 若 `days_remaining = -1`，表示**长期有效**，不是过期

## 10.5 打开 Swagger 页面

浏览器访问：

```text
http://<服务器IP>:8080/docs
```

用于：

- 查看接口
- 在线调试
- 现场联调验证

---

## 11. 推荐的现场验收命令清单

建议现场至少执行以下命令：

```bash
curl http://localhost:8080/api/v1/health
curl http://localhost:8080/api/v1/capabilities
curl http://localhost:8080/api/v1/license/status
```

如果客户现场已交付图片推理接口，再至少验证一个实际业务接口，例如：

```bash
curl -X POST "http://localhost:8080/api/v1/infer/detect_fake_photo" \
  -F "image=@test.jpg"
```

或：

```bash
curl -X POST "http://localhost:8080/api/v1/infer/detect_face_property" \
  -F "image=@face.jpg"
```

---

## 12. 升级操作

## 12.1 升级整镜像

```bash
cd /opt/ai_platform_deploy
docker compose -f docker-compose.prod.yml down
docker load -i agilestar_ai_prod_vnext.tar
docker compose -f docker-compose.prod.yml up -d
```

说明：

- 升级镜像时，宿主机目录中的授权、模型、动态库、pipeline 通常无需重新准备
- 只要挂载目录不变，升级后容器会继续读取宿主机中的现场资源

## 12.2 仅升级模型或动态库

替换宿主机目录中的文件后，执行：

```bash
cd /opt/ai_platform_deploy
docker compose -f docker-compose.prod.yml restart prod
```

或者使用热重载接口：

```bash
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer <AI_ADMIN_TOKEN>"
```

单能力热重载：

```bash
curl -X POST http://localhost:8080/api/v1/admin/reload/<capability> \
  -H "Authorization: Bearer <AI_ADMIN_TOKEN>"
```

---

## 13. 回滚操作

如果升级后异常，可快速回滚：

```bash
cd /opt/ai_platform_deploy
docker compose -f docker-compose.prod.yml down
docker load -i agilestar_ai_prod_previous.tar
docker compose -f docker-compose.prod.yml up -d
```

如果仅是模型或动态库升级导致问题，则将宿主机目录恢复到上一版后重启容器即可。

---

## 14. 最常见的 5 个问题

## 14.1 容器启动成功，但 `/api/v1/health` 不正常

排查：

```bash
docker compose -f docker-compose.prod.yml logs -f prod
```

检查：

- 动态库是否齐全
- `libai_runtime.so` 是否正确交付
- 模型目录是否完整
- 授权文件是否存在

## 14.2 `/api/v1/capabilities` 为空

通常表示能力未成功加载。重点检查：

- 模型目录里是否有 `manifest.json`
- `current/` 是否指向正确版本
- 动态库是否放对目录

## 14.3 提示 `Capability version not licensed`

说明能力版本与授权不匹配。重点检查：

- 模型版本
- 动态库版本
- license 覆盖范围

## 14.4 `days_remaining = -1`

不是错误。

表示：

- **长期有效**

## 14.5 GPU 服务器没有走 GPU

检查：

- `nvidia-smi` 是否正常
- NVIDIA Container Toolkit 是否安装完成
- 容器日志是否检测到 GPU

---

## 15. 一页式速查表

## 15.1 常用路径

| 项目 | 路径 |
|---|---|
| 宿主机根目录 | `/data/ai_platform` |
| 授权目录 | `/data/ai_platform/licenses` |
| 模型目录 | `/data/ai_platform/models` |
| 动态库目录 | `/data/ai_platform/libs/linux_x86_64` |
| pipeline 目录 | `/data/ai_platform/pipelines` |
| 日志目录 | `/data/ai_platform/logs/prod` |
| 部署目录 | `/opt/ai_platform_deploy` |

## 15.2 最少交付物

| 项目 | 说明 |
|---|---|
| `agilestar_ai_prod_latest.tar` | 生产镜像离线包 |
| `docker-compose.prod.yml` | 启动配置文件 |
| `license.bin` | 客户授权文件 |
| `pubkey.pem` | 授权校验公钥 |
| `models/` | 客户所需模型资源 |
| `libs/` | 客户所需动态库资源 |

## 15.3 常用接口

| 接口 | 用途 |
|---|---|
| `GET /api/v1/health` | 健康检查 |
| `GET /api/v1/capabilities` | 查看能力加载状态 |
| `GET /api/v1/license/status` | 查看授权状态 |
| `POST /api/v1/infer/{capability}` | 调用单能力接口 |
| `POST /api/v1/admin/reload` | 热重载全部能力 |
| `POST /api/v1/admin/reload/{capability}` | 热重载单个能力 |
| `/docs` | Swagger 页面 |

---

## 16. 最终结论

客户现场部署时，记住三件事即可：

- **镜像要导入成功**
- **授权、模型、动态库要放对目录**
- **启动后必须检查 `health`、`capabilities`、`license/status`**

本版本手册适用于**完全离线交付场景**，不依赖项目源码仓库。

只要以上三项正确，生产镜像即可运行。
