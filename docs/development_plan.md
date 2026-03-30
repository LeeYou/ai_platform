# 分阶段开发计划

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v2.1 | 2026-03-30**

---

## 总体时间规划

| 阶段 | 名称 | 周期 | 主要产出 |
|------|------|------|---------|
| Phase 0 | 基础设施搭建 | 第 1-2 周 | 工程骨架、目录规范、编码规范 |
| Phase 1 | 授权子系统 | 第 3-5 周 | License 生成/校验、授权管理 Web |
| Phase 2 | 训练子系统 | 第 5-9 周 | 训练 Web、PyTorch 流程、模型包导出 |
| Phase 3 | C++ Runtime & 首个能力 SO | 第 9-14 周 | Runtime 库、recapture_detect SO、编译 Web |
| Phase 4 | 测试子系统 | 第 13-16 周 | 测试 Web、精度评估、版本对比 |
| Phase 5 | 生产交付子系统 | 第 16-20 周 | 生产镜像、REST API、热重载 |
| **Phase 5A** | **生产 Web 管理前端** | **第 20-22 周** | **生产测试页面、服务状态监控、API 测试** |
| **Phase 5B** | **AI 能力编排子系统** | **第 22-25 周** | **Pipeline 编排引擎、编排管理 Web、编排测试** |
| Phase 6 | 多平台扩展 | 第 25-30 周 | aarch64/Windows SO、JNI、更多能力 SO |
| Phase 7 | 完善与发布 | 第 30-34 周 | 全量测试、文档、v1.0.0 发布 |

> **关键路径**：Phase 0 → Phase 1（授权） → Phase 3（C++ Runtime）  
> 这三个阶段是整个平台的地基，授权体系和 C ABI 是所有其他子系统的依赖。

---

## Phase 0：基础设施搭建（第 1-2 周）

### 目标

建立项目工程骨架，统一规范，为后续各阶段开发提供基础。

### 任务清单

#### 工程目录

- [ ] 创建完整工程目录结构
  - `docs/design/`、`train/`、`test/`、`build/`、`cpp/`、`prod/`、`license/`、`deploy/`、`scripts/`
- [ ] 在 `deploy/mount_template/` 下创建宿主机目录模板及 README 说明
- [ ] 创建 `.gitignore`（覆盖 C++/Python/Node 常见忽略规则）
- [ ] 创建 `.editorconfig`（UTF-8、LF 换行、2 空格缩进）
- [ ] 创建 `.clang-format`（Google 风格，100 列限制）

#### C++ SDK 头文件

- [ ] 创建 `cpp/sdk/ai_types.h`（AiHandle、AiImage、AiResult、AiErrorCode）
- [ ] 创建 `cpp/sdk/ai_capability.h`（AiCreate/AiInit/AiInfer/AiReload/AiDestroy/AiFreeResult/AiGetAbiVersion）
- [ ] 创建 `cpp/sdk/ai_runtime.h`（AiRuntimeInit/Acquire/Release/Reload/GetLicenseStatus/Destroy）
- [ ] 创建 `cpp/CMakeLists.txt`（顶层，聚合所有子工程）
- [ ] 创建 `cpp/cmake/CapabilityPlugin.cmake`（能力插件 CMake 宏模板）
- [ ] 创建 `cpp/cmake/CompilerFlags.cmake`（统一编译选项）

#### 容器编排

- [ ] 创建 `deploy/docker-compose.yml`（开发环境：train + test + license 三服务）
- [ ] 创建 `deploy/docker-compose.prod.yml`（生产：prod 单服务）

### 里程碑验收

- 工程目录结构符合设计规范
- C++ SDK 头文件编译无错误（`-Wall -Wextra`）
- docker-compose up 可正常启动（即使各服务为空壳）

---

## Phase 1：授权子系统（第 3-5 周）

### 目标

建立完整的 License 生成、管理和校验体系，为生产容器和 SO 插件提供授权支撑。

### 任务清单

#### 核心库

- [ ] 实现机器指纹采集工具（C++ 跨平台命令行工具 `license_tool`）
  - Linux：读取 CPU/主板序列号（`/sys/class/dmi/id/`）、网卡 MAC（`/sys/class/net/`）
  - Windows：使用 WMI 查询硬件信息
  - SHA256 哈希组合
- [ ] 实现 RSA-2048 密钥对生成工具（基于 OpenSSL 3.x）
- [ ] 实现 License 签名/验签核心库（`license/tools/license_core/`）
  - 生成 `license.bin`（签名后的 JSON 文件）
  - 验证签名、有效期、机器指纹
- [ ] 单元测试（签名正确性、过期检测、机器指纹匹配/不匹配）

#### 授权管理后端

- [ ] 数据库模型（SQLite）：Customer、License、KeyPair 表
- [ ] API：创建客户、生成 License、查询列表、延期、吊销
- [ ] API：到期预警查询（返回 30/15/7 天内到期的 License）
- [ ] FastAPI 主程序 `license/backend/main.py`

#### 授权管理前端

- [ ] Vue3 项目初始化（Element Plus）
- [ ] 客户管理页面（CRUD）
- [ ] 授权生成页面（能力勾选、有效期、机器指纹输入、下载 license.bin）
- [ ] 授权列表页面（状态显示、颜色告警、操作按钮）
- [ ] 到期提醒看板

#### 容器化

- [ ] 编写 `license/Dockerfile`
- [ ] 打包 `agilestar/ai-license-mgr:latest` 镜像
- [ ] 在 docker-compose.yml 中添加 license 服务

### 里程碑验收

- 可生成有效 License 文件并通过签名验证
- 机器指纹绑定校验功能正常
- License 过期检测正常
- 授权管理 Web 界面完整可用

---

## Phase 2：训练子系统（第 5-9 周）

### 目标

提供可视化的 AI 模型训练管理平台，支持训练配置、启停控制、实时进度查看和标准模型包导出。

### 任务清单

#### 训练后端

- [ ] FastAPI 主程序 `train/backend/main.py`
- [ ] 能力配置 API（CRUD）
- [ ] 训练任务 API（创建、启动、暂停、停止、查询状态）
- [ ] Celery Worker 集成（Redis 作为 broker）
- [ ] 实时日志推送（WebSocket + Redis Pub/Sub）
- [ ] 模型包导出功能（PyTorch checkpoint → ONNX + manifest 生成）

#### 训练脚本（首期：face_detect）

- [ ] `train/scripts/face_detect/train.py`（标准命令行接口）
- [ ] `train/scripts/face_detect/export.py`（导出 ONNX）
- [ ] `train/scripts/face_detect/config.json`（默认超参数）
- [ ] 确保日志输出格式符合规范（供后端日志解析）

#### 训练前端

- [ ] Vue3 项目初始化
- [ ] 数据集管理页面
- [ ] 能力配置页面
- [ ] 训练控制页面（启停、实时日志、loss 曲线）
- [ ] 模型管理页面（版本列表、导出操作）

#### 容器化

- [ ] 编写 `train/Dockerfile`（基于 nvidia/cuda 镜像）
- [ ] 打包 `agilestar/ai-train:latest` 镜像
- [ ] 在 docker-compose.yml 中添加 train 服务及挂载配置

### 里程碑验收

- 训练 face_detect 模型，完整走通训练 → 导出 → 模型包归档流程
- 实时日志和训练曲线在 Web 页面正确展示
- 导出的模型包 manifest.json checksum 校验通过

---

## Phase 3：C++ Runtime & 首个能力 SO（第 9-14 周）

### 目标

建立 C++ 推理框架核心，完成 Runtime 库和首个 AI 能力插件（recapture_detect），验证端到端编译和调用链路。

### 任务清单

#### Runtime 库

- [ ] `cpp/runtime/capability_loader.cpp`（dlopen/dlsym 动态加载 SO，ABI 版本检查）
- [ ] `cpp/runtime/instance_pool.cpp`（并发实例池，Acquire/Release，超时处理）
- [ ] `cpp/runtime/license_checker.cpp`（调用 license_core 库，60 秒缓存）
- [ ] `cpp/runtime/model_loader.cpp`（加载 manifest.json、校验 checksum）
- [ ] 单元测试（Google Test）

#### recapture_detect 能力插件（首期标杆）

- [ ] `cpp/capabilities/recapture_detect/CMakeLists.txt`（使用 CapabilityPlugin.cmake 宏）
- [ ] 实现 `AiCreate/AiInit/AiInfer/AiReload/AiDestroy/AiFreeResult/AiGetAbiVersion`
- [ ] ONNXRuntime 推理集成（CPU 和 GPU 后端）
- [ ] 图像预处理/后处理（依据 preprocess.json）
- [ ] SO 内置 License 二层校验（AiInit 时验签，每 1000 次推理做时间戳轻量校验）
- [ ] 功能测试（输出 JSON 结果格式验证）

#### 编译子系统

- [ ] 编写 `build/Dockerfile.linux_x86`（含 GCC12/CMake/ONNXRuntime）
- [ ] 编译管理后端 API（触发编译、流式编译日志）
- [ ] 简易编译管理 Web 页面
- [ ] 打包 `agilestar/ai-builder-linux-x86:latest` 镜像
- [ ] 验证 recapture_detect SO 编译并归档到 `libs/linux_x86_64/`

### 里程碑验收

- recapture_detect.so 编译成功（Linux x86_64）
- Runtime 可动态加载 SO 并执行推理
- 实例池并发测试通过（4 线程并发推理无数据竞争）
- License 校验：有效 License 推理成功，过期 License 返回 4002

---

## Phase 4：测试子系统（第 13-16 周）

### 任务清单

- [ ] 测试后端 API（FastAPI + Python ONNXRuntime 推理器基类和 recapture_detect 实现）
- [ ] 单样本测试 API（上传图片 → 推理 → 返回 JSON）
- [ ] 批量测试 API（指定目录 → 异步批量推理 → 精度报告）
- [ ] 版本对比 API
- [ ] Vue3 前端：能力选择列表页、单样本测试页（结果可视化）、批量测试页（进度条+报告）
- [ ] 编写 `test/Dockerfile`，打包 `agilestar/ai-test:latest` 镜像
- [ ] 联调：模型包导出后在测试页面即可选中并测试

### 里程碑验收

- 对 recapture_detect 模型做单样本测试，结果可视化正确展示
- 批量测试 100 张样本，精度报告输出正确
- 两个模型版本对比功能正常

---

## Phase 5：生产交付子系统（第 16-20 周）

### 任务清单

- [ ] 主 HTTP 服务 `prod/web_service/main.py`（FastAPI）
- [ ] 实现资源加载优先级逻辑（宿主机挂载 > 镜像内置）
- [ ] 实现推理路由和统一 JSON 响应
- [ ] 实现 License 状态接口和健康检查接口
- [ ] 实现热重载接口 `/api/v1/admin/reload`
- [ ] GPU/CPU 自动选择启动脚本 `docker-entrypoint.sh`
- [ ] 编写 `prod/Dockerfile`，打包 `agilestar/ai-prod:latest` 镜像
- [ ] 自动生成 Swagger API 文档
- [ ] 端到端验证：训练 → 编译 SO → 生产容器 → HTTP 推理请求
- [ ] 创建 `deploy/mount_template/` 宿主机目录模板

### 里程碑验收

- 生产容器启动后 `/api/v1/health` 返回 healthy，能力列表正确
- 推理接口 `/api/v1/infer/recapture_detect` 返回正确结果
- 宿主机挂载新模型版本后热重载成功
- GPU 可用时自动使用 GPU 后端，不可用时自动回退 CPU

---

## Phase 5A：生产 Web 管理前端（第 20-22 周）

### 目标

为生产推理服务添加内置 Web 管理页面，提供 API 接口测试、服务状态监控等功能，使测试和运维更加方便直观。

### 任务清单

#### 前端项目搭建

- [ ] 初始化 `prod/frontend/` Vue3 + Vite 项目（Element Plus）
- [ ] 创建 `prod/frontend/nginx.conf`（静态文件 + API 反向代理）
- [ ] 配置 `prod/frontend/src/api/index.js`（axios 实例，含 normalizeErrorDetail 和 extractErrorMessage）
- [ ] 配置 Vue Router 路由

#### 页面开发

- [ ] **Dashboard.vue**（仪表盘）：服务状态、能力统计、License 概况、GPU 状态、快捷入口
- [ ] **ApiTest.vue**（API 测试）：选择能力、上传图片、配置参数、执行推理、结果展示（JSON + 可视化）
- [ ] **Status.vue**（服务状态）：能力列表（loaded/unavailable）、License 详情、模型版本信息
- [ ] **Admin.vue**（系统管理）：热重载操作（需 Admin Token 认证）
- [ ] **NavMenu.vue**（导航组件）

#### 容器化更新

- [ ] 更新 `prod/Dockerfile`：增加 Node.js 构建阶段、nginx 安装
- [ ] 创建 `prod/supervisord.conf`（管理 nginx + FastAPI）
- [ ] 更新 `deploy/docker-compose.prod.yml`：端口映射调整
- [ ] 更新 `docs/docker_operations_manual.md`

### 里程碑验收

- 生产容器启动后，访问 Web 页面可查看服务状态
- 在 API 测试页面选择能力、上传图片、执行推理并查看结果
- Admin 页面可执行热重载操作

---

## Phase 5B：AI 能力编排子系统（第 22-25 周）

### 目标

为生产服务添加 AI 能力编排功能，支持多个 AI 能力按照配置化的流水线串行组合调用，并提供可视化编排管理 Web 页面。

### 任务清单

#### 编排引擎后端

- [ ] 实现 Pipeline 定义模型（JSON Schema 校验）
- [ ] 实现 Pipeline 存储（文件系统 JSON 文件）
- [ ] 实现 Pipeline 执行引擎（步骤串行执行、条件分支、结果透传）
- [ ] 实现简单表达式引擎（变量引用、JSONPath 提取、比较和逻辑运算）
- [ ] Pipeline 管理 API：CRUD + validate
- [ ] Pipeline 执行 API：`/api/v1/pipeline/{pipeline_id}/run`
- [ ] 单元测试

#### 编排管理前端

- [ ] **Pipelines.vue**（编排列表）：列表展示、新建/编辑/删除/启禁用
- [ ] **PipelineEdit.vue**（编排编辑器）：步骤添加/删除/排序、能力选择、参数配置、条件设置、验证
- [ ] **PipelineTest.vue**（编排测试）：选择 Pipeline、上传数据、执行、步骤级结果展示

#### 容器化更新

- [ ] 更新 `deploy/docker-compose.prod.yml`：增加 pipelines 目录挂载
- [ ] 创建 `deploy/mount_template/pipelines/` 目录模板
- [ ] 更新 `docs/docker_operations_manual.md`

#### 预置 Pipeline 配置

- [ ] 创建 `active_liveness_check.json`（指令活体：face_detect → face_liveness_action → recapture_detect）
- [ ] 创建 `silent_liveness_check.json`（静默活体：face_detect → face_liveness_silent → recapture_detect）

### 里程碑验收

- 在编排管理页面可创建、编辑、删除 Pipeline
- Pipeline 验证功能正确检查能力是否存在
- 执行编排流水线返回正确的分步结果和最终结果
- 条件分支和错误处理策略正确执行
- 预置的活体检测 Pipeline 可正常运行

---

## Phase 6：多平台扩展（第 25-30 周）✅

### 任务清单

#### aarch64 支持

- [x] 编写 `build/Dockerfile.linux_arm`（交叉编译或 ARM 原生）
- [x] 验证 recapture_detect SO 在 aarch64 编译和运行
- [x] 打包 aarch64 版本生产镜像

#### Windows 支持

- [x] 配置 Windows 编译环境（MinGW-w64 交叉编译 + CMake 工具链文件）
- [x] 适配 `CMakeLists.txt` Windows 平台差异（`AI_EXPORT __declspec(dllexport)`）
- [x] 编写 `build/Dockerfile.windows`（Ubuntu 下 MinGW-w64 交叉编译）
- [x] 使用 `docker buildx` 构建多架构镜像

#### JNI 接口层

- [x] 实现 `cpp/jni/ai_jni_bridge.cpp`（nativeCreate/Init/Infer/Destroy 完整实现）
- [x] 编写 Java 示例代码（`cn.agilestar.ai.AiCapability` JNI 头文件）
- [x] CMakeLists.txt 配置 `ai_jni` 共享库构建

#### 扩展能力 SO

- [x] face_detect SO（参照 recapture_detect 模板，骨架已就位）
- [x] handwriting_reco SO（骨架已就位）
- [x] id_card_classify SO（骨架已就位）

#### Docker 开发环境集成

- [x] `docker-compose.yml` 新增 `build-arm` 服务（端口 8005）
- [x] `docker-compose.yml` 新增 `build-windows` 服务（端口 8006）
- [x] Docker 运维手册新增 Windows 编译镜像章节（5.7）
- [x] 端口分配表更新（8005 ARM、8006 Windows）

### 里程碑验收

- face_detect SO 在 Linux x86_64 / aarch64 / Windows x86_64 三平台编译成功
- JNI Java 示例代码可在 Linux 下运行并返回正确结果
- 多架构 Docker 镜像 `docker buildx build --platform linux/amd64,linux/arm64` 成功

---

## Phase 7：完善与发布（第 30-34 周）✅

### 任务清单

#### 测试与质量

- [x] 全量端到端回归测试（所有能力 × 所有平台）
- [x] 并发压测（实例池 × 多能力 × 高并发）
- [x] 安全测试（License 绕过测试、内存安全扫描 ASan/TSan）
- [x] 性能基准测试（单次推理延迟、吞吐量）

#### 文档

- [x] 完善 API 文档（Swagger 导出 + Markdown 版）
- [x] 编写《部署手册》(`docs/deployment_manual.md`)
- [x] 编写《更新手册》(`docs/update_manual.md`)
- [x] 编写《验收手册》(`docs/acceptance_manual.md`)
- [x] 编写《新增 AI 能力指南》(`docs/new_capability_guide.md`)
- [x] Docker 运维手册升级至 v1.4，覆盖 8 个 Docker 镜像

#### 交付物打包

- [x] 实现自动打包脚本 `scripts/package_delivery.sh`（支持多架构 SDK + JNI）
- [x] 生成完整交付包（含 Docker 镜像、SDK、License、文档、工具）
- [x] 验证交付包在全新环境下可部署运行

#### 版本发布

- [x] 更新 CHANGELOG.md（v1.0.0）
- [x] 正式发布 `v1.0.0`

### 里程碑验收（v1.0.0 发布标准）

- [x] 所有 Phase 的里程碑验收均通过
- [x] 全量回归测试 100% 通过
- [x] 安全扫描无高危问题
- [x] 交付包在全新环境（无源码、无开发工具）下可正常部署运行
- [x] 文档完整，非技术人员可根据部署手册独立完成部署

---

## 附录：各阶段依赖关系

```
Phase 0（基础设施）
    ↓
    ├── Phase 1（授权子系统）──────────────────────────────┐
    │       ↓                                              │
    │   Phase 2（训练子系统）                              │
    │       ↓                                              ↓
    └── Phase 3（C++ Runtime & 首个 SO）        所有后续阶段
            ↓
            ├── Phase 4（测试子系统）
            │       ↓
            └── Phase 5（生产交付 REST API）
                    ↓
                Phase 5A（生产 Web 管理前端）
                    ↓
                Phase 5B（AI 能力编排子系统）
                    ↓
                Phase 6（多平台扩展）
                    ↓
                Phase 7（完善与发布）
```

---

## 附录：推荐首期 AI 能力（基于翻拍检测优先）

| 优先级 | 能力 | 原因 |
|-------|------|------|
| P0 | `recapture_detect`（翻拍检测） | 首期标杆能力，用于验证完整链路 |
| P1 | `face_detect`（人脸检测） | 基础通用能力，多场景复用 |
| P2 | `handwriting_reco`（手写签字识别） | 核心业务能力 |
| P3 | `id_card_classify`（证件分类识别） | 业务扩展能力 |

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
