# 更新日志

本文件基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

## [1.2.0] - 2026-03-30

### 文档 (Documentation)

- 新增 `docs/desktop_recapture_detect_guide.md` — 桌面翻拍检测能力专用操作指南
  - 覆盖素材准备、假样本生成、模型训练、评估、ONNX 导出、测试、编译、部署全流程
  - 包含 API 调用示例、训练超参数说明、假样本生成详解、常见问题及性能基准
  - 遵循与 `face_detect_guide.md` 相同的文档结构模板

## [1.1.0] - 2026-03-30

### 新增 (Added)

- **样本标注子系统** — 在训练容器中集成完整的样本标注功能
  - 支持五种标注类型：二分类、多分类、目标检测(YOLO)、OCR文字识别、图像分割
  - 标注项目管理：关联 AI 能力、标注类型、神经网络选型
  - 标注工作台：大图展示、工具栏、样本导航、进度追踪
  - 键盘快捷键：数字键标注、方向键翻页、自动跳转下一样本
  - 多格式导出：分类目录结构、YOLO txt、OCR txt、通用 JSON
  - 安全设计：路径遍历防护、JSON 格式校验

### 文档 (Documentation)

- 新增 `docs/design/annotation_service.md` 标注子系统设计文档
- 更新 `docs/design/architecture.md` v2.1 — 新增标注子系统说明
- 更新 `docs/design/train_service.md` v1.1 — 新增标注页面和流程
- 更新 `docs/development_plan.md` v2.2 — 新增 Phase 8 标注子系统

## [1.0.0] - 2026-03-30

### 新增

- **多平台支持（阶段 6）**：新增 `build/Dockerfile.windows` 支持 Windows x86_64 交叉编译（MinGW-w64）
- **多平台支持（阶段 6）**：新增 `build/Dockerfile.linux_arm` 支持 aarch64/ARM64 交叉编译
- **多平台支持（阶段 6）**：JNI 接口层完整实现 (`cpp/jni/ai_jni_bridge.cpp`)，支持 Java/Android 集成
- **多平台支持（阶段 6）**：`docker-compose.yml` 新增 `build-arm` 与 `build-windows` 服务
- **多平台支持（阶段 6）**：交付打包脚本支持多架构 SDK 头文件与 JNI 头文件
- **AI 编排（阶段 5B）**：流水线引擎，支持多能力串行 / 并行组合调度
- **AI 编排（阶段 5B）**：流水线 CRUD、校验、运行 REST API
- **AI 编排（阶段 5B）**：Vue3 流水线管理页面（创建、编辑、运行、日志查看）
- **AI 编排（阶段 5B）**：预置流水线模板（活体检测、静默活体检测等）
- **生产前端（阶段 5A）**：Dashboard 总览页、API 调试页、服务状态页、管理员页面
- **生产交付（阶段 5）**：FastAPI 推理服务，支持 REST API 统一调用
- **生产交付（阶段 5）**：资源解析器，自动发现挂载目录中的模型与 SO 文件
- **生产交付（阶段 5）**：GPU / CPU 自动检测与推理后端切换
- **生产交付（阶段 5）**：Docker 入口脚本与健康检查机制
- **测试子系统（阶段 4）**：单条 / 批量测试功能
- **测试子系统（阶段 4）**：模型版本对比评估
- **测试子系统（阶段 4）**：Vue3 测试管理前端
- **C++ 运行时（阶段 3）**：`libai_runtime` 核心运行时库（动态加载、实例池、许可校验、模型加载）
- **C++ 运行时（阶段 3）**：统一 C ABI 插件接口 (`ai_capability.h`，ABI_VERSION = 10000)
- **C++ 运行时（阶段 3）**：首批能力 SO 插件——recapture_detect、face_detect、handwriting_reco、id_card_classify
- **C++ 运行时（阶段 3）**：CMake 插件宏 `CapabilityPlugin.cmake`，一键构建能力 SO
- **C++ 运行时（阶段 3）**：108 项 AI 能力插件骨架代码
- **C++ 运行时（阶段 3）**：构建服务后端及 Vue3 构建管理前端
- **C++ 运行时（阶段 3）**：x86_64 Docker 构建容器 (`build/Dockerfile.linux_x86`)
- **训练子系统（阶段 2）**：FastAPI 训练后端（任务管理、Celery 异步队列、Redis 状态存储）
- **训练子系统（阶段 2）**：107 项能力训练脚本（覆盖人脸、OCR、NLP、语音、视频等方向）
- **训练子系统（阶段 2）**：Vue3 训练管理前端
- **训练子系统（阶段 2）**：训练 / 开发双 Dockerfile（PyTorch + PaddlePaddle 环境）
- **许可子系统（阶段 1）**：RSA-2048 密钥对管理与许可证签发 / 验证
- **许可子系统（阶段 1）**：机器指纹绑定与双层校验机制
- **许可子系统（阶段 1）**：许可证模板与编译工具 (`license_build/`)
- **许可子系统（阶段 1）**：Vue3 许可证管理前端
- **基础设施（阶段 0）**：项目目录结构与 monorepo 规范
- **基础设施（阶段 0）**：Docker Compose 开发 / 生产编排 (`deploy/`)
- **基础设施（阶段 0）**：`.editorconfig`、`.clang-format`（Google 风格）、`.gitignore` 等工程配置
- **基础设施（阶段 0）**：平台级脚本——镜像构建推送、健康检查、交付打包、公钥指纹计算

### 文档

- 系统架构设计文档 (`docs/design/architecture.md`)
- 各子系统设计文档（训练、测试、构建、生产、许可、C++ ABI、AI 编排、生产前端）
- C++ 编码规范 (`docs/cpp_coding_standard.md`)
- 七阶段开发路线图 (`docs/development_plan.md`)
- Docker 运维手册 v1.4 (`docs/docker_operations_manual.md`)，覆盖 8 个 Docker 镜像
- 部署手册 (`docs/deployment_manual.md`)
- 更新手册 (`docs/update_manual.md`)
- 验收手册 (`docs/acceptance_manual.md`)
- 新增 AI 能力开发者指南 (`docs/new_capability_guide.md`)
- 105 项 AI 能力市场概览 (`docs/ai_capability_market_overview.md`)
- 性能优化路线图 (`docs/optimization_plan.md`)

---

[1.2.0]: https://github.com/AgileStar/ai_platform/releases/tag/v1.2.0
[1.1.0]: https://github.com/AgileStar/ai_platform/releases/tag/v1.1.0
[1.0.0]: https://github.com/AgileStar/ai_platform/releases/tag/v1.0.0
