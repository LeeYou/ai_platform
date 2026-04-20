# 更新日志

本文件基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

## [Unreleased]

### 新增 (Added)

- **ai_agface 迁移（第四轮）** — 加入 barehead / fake_photo / face_property 三类 NCNN 能力
  - 新能力插件 `cpp/capabilities/agface_barehead/`
  - 新能力插件 `cpp/capabilities/agface_fake_photo/`
  - 新能力插件 `cpp/capabilities/agface_face_property/`
  - `_agface_common` 扩展：
    - `vision_analysis_common.h/.cpp` — legacy heuristic 与图像预处理
    - `legacy_vision_context.h/.cpp` — shared NCNN resource loading / live / attr / mesh / hat helpers
  - 新构建选项 `BUILD_CAP_AGFACE_BAREHEAD` / `BUILD_CAP_AGFACE_FAKE_PHOTO` /
    `BUILD_CAP_AGFACE_FACE_PROPERTY`
  - 新模型迁移脚本 `scripts/migrate_agface_vision_models.py`
  - 新 ABI 烟雾测试 `tests/prod/test_agface_vision_plugins.py`

- **ai_agface 迁移（第三轮）** — 加入 MobileFaceNet + Python 端到端比对
  - 新能力插件 `cpp/capabilities/agface_face_feature_mobilenet256/`
    （NCNN MobileFaceNet 256 维，output blob 为 `fc1`；复用 `feature_plugin_impl.h`）
  - 构建选项 `BUILD_CAP_AGFACE_FACE_FEATURE_MOBILENET256`
  - 模型迁移脚本 `scripts/migrate_agface_face_feature_models.py` 扩展 `--which mobilenet256`
  - **新 HTTP 端点 `POST /api/v1/agface/face_compare`** — 端到端两图比对，
    编排 `agface_face_detect`（可选）→ 取最大人脸 crop → `agface_face_feature_*` ×2 →
    cosine + 分段映射 0-100 分。替代旧 `agface_compare_jpg` SDK 入口
  - 新模块 `prod/web_service/agface_compare.py` —— 纯 Python 零依赖编排层，
    提供 `cosine_similarity` / `calibrate_score` / `pick_largest_face_bbox` /
    `crop_image_to_bbox` / `compare_faces`
  - `prod/web_service/main.py` 新增 `_encode_image_jpeg` 辅助函数
  - 单元测试 `tests/prod/test_agface_compare.py`（6 个分段锚点 + 编排路径）
  - 烟雾测试 `tests/prod/test_agface_feature_plugins.py` 扩展覆盖 mobilenet256

- **ai_agface 迁移（第二轮）** — 加入人脸特征提取能力
  - 新能力插件 `cpp/capabilities/agface_face_feature_residual256/`（NCNN Residual 256 维）
  - 新能力插件 `cpp/capabilities/agface_face_feature_glint512/`（NCNN Glint360K-R34 512 维）
  - `_agface_common` 扩展：
    - `face_align.h/.cpp` — 5 点相似变换对齐到 112×112（闭合解 + 双线性，与旧算法等价）
    - `feature_extract.h/.cpp` — 共用特征提取流水（对齐 → 预处理 → forward → L2 归一化）
    - `feature_plugin_impl.h` — 全套 `Ai*` ABI 模板头，feature 插件单 `#include` 复用
    - `manifest.h` 新增 `feature_dim` 字段（输出维度自检）
  - 新构建选项 `BUILD_CAP_AGFACE_FACE_FEATURE_RESIDUAL256` / `BUILD_CAP_AGFACE_FACE_FEATURE_GLINT512`
  - 模型迁移脚本 `scripts/migrate_agface_face_feature_models.py`（`--which` 选 residual256/glint512/all）
  - 烟雾测试 `tests/prod/test_agface_feature_plugins.py`（ABI 版本 / NULL 安全 / manifest 容错）
  - 架构决策：`agface_face_align` 内化到 feature 插件；`agface_face_compare` 由客户端做点积 + 分段映射；
    composite capability 与 JNI 兼容层列入第三轮

- **ai_agface 迁移（MVP）** — 旧人脸比对 SDK 合并入当前能力插件体系
  - 新构建选项 `BUILD_CAP_AGFACE_FACE_DETECT` / `BUILD_ALL_AGFACE_CAPS`
  - `add_capability_plugin()` 宏新增 `BACKEND ONNX|NCNN|NONE` 与 `EXTRA_LIBS` 关键字
  - 新 FindModule：`cpp/cmake/FindNCNN.cmake`（支持 vendored / system / NCNN_ROOT 三级回退）
  - 共享适配层 `cpp/capabilities/_agface_common/`（NcnnSession、InstancePool、
    manifest.json 解析、AiImage→cv::Mat、AiResult JSON 填充）
  - 首个能力插件 `cpp/capabilities/agface_face_detect/`（NCNN RetinaFace SSD 头），
    完整实现 `@/cpp/sdk/ai_capability.h` 约定的 `Ai*` ABI
  - 模型迁移脚本 `scripts/migrate_agface_face_detect_model.py`（生成标准
    `<dst>/agface_face_detect/1.0.0/{detection.param,bin,manifest.json}`，含 sha256）
  - Docker 基础镜像新增 `libncnn-dev/libncnn1 + libopencv + libomp` 依赖
  - 迁移设计文档 `docs/design/agface_migration.md` —— 旧→新模块映射、丢弃清单、
    验收命令、后续迁移计划

## [1.3.0] - 2026-03-31

### 新增 (Added)

- **模型校验和验证** — 生产推理引擎自动验证模型完整性
  - 在模型加载时自动检查 `checksum.sha256` 文件
  - SHA256 哈希验证防止模型文件损坏或篡改
  - 校验失败时抛出 RuntimeError 并拒绝加载
  - 开发/测试模式下无 checksum 文件则跳过验证

- **性能剖析增强** — 推理结果包含详细的性能分解数据
  - 新增 `performance` 字段包含三个阶段耗时：
    - `preprocess_ms`: 图像预处理耗时
    - `inference_ms`: 模型推理耗时
    - `postprocess_ms`: 后处理耗时
  - 便于识别性能瓶颈并针对性优化
  - 所有耗时精确到 0.01 毫秒

- **A/B 测试框架** — 支持多模型版本的灰度发布和流量分配
  - 基于权重的随机流量分配策略
  - 基于会话 ID 的粘性会话策略（用户体验一致）
  - JSON 配置文件热重载（无需重启服务）
  - 管理 API：查看活动测试、重新加载配置
  - 推理响应包含 `_ab_test_version` 用于分析
  - 配置示例：70% v1.0.0 + 30% v1.1.0 灰度发布

- **CI/CD 自动化流水线** — 完整的 GitHub Actions 工作流
  - 多平台 Docker 镜像构建验证（train/test/license/prod）
  - Builder 镜像构建验证（linux_x86/linux_arm）
  - Python 代码质量检查（flake8, mypy, black, isort）
  - 前端构建测试（4 个 Vue3 应用）
  - C++ SDK 和 Runtime 构建验证
  - 模型包结构完整性检查
  - 文档完整性验证
  - Docker Compose 配置验证
  - 安全漏洞扫描（Trivy）

### 文档 (Documentation)

- 新增 `docs/troubleshooting_guide.md` — 全面的故障排查指南
  - 20+ 常见问题诊断和解决方案
  - 覆盖 Docker 构建、训练、测试、授权、编译、生产推理
  - 性能问题诊断和网络连接问题
  - 包含完整的命令示例和配置建议
  - 紧急恢复步骤和数据备份指南

- 新增 `docs/performance_optimization_guide.md` — 性能优化最佳实践
  - 推理性能优化：GPU 加速、TensorRT、模型量化、实例池调优
  - 训练性能优化：混合精度、数据加载、分布式训练、梯度累积
  - Docker 容器优化：共享内存、资源限制、日志轮转
  - 网络和 I/O 优化：文件系统选择、数据集缓存、HTTP 连接池
  - 资源配置建议：小/中/大规模部署方案
  - 监控和诊断工具：性能分析、GPU 监控、基准测试

- 新增 `.github/workflows/ci.yml` — CI/CD 配置文档（YAML 即文档）

### 改进 (Improved)

- **Docker 构建优化** — 使用国内镜像源加速构建
  - pip 使用清华大学镜像源（下载速度提升 50-100 倍）
  - npm 使用淘宝镜像源（下载速度提升 20-30 倍）
  - 优化层缓存策略（源代码改动不触发依赖重新下载）
  - 首次构建时间从 30-60 分钟降低到 3-5 分钟

- **训练管理 Web UI 增强** — 专业级训练监控和管理界面
  - 实时训练进度显示（Epoch X/Y 进度条）
  - 实时指标显示（loss、accuracy、speed、ETA）
  - 专业监控仪表板（4 状态卡片 + 双图表）
  - Loss 和 Accuracy 曲线图（渐变填充、实时更新）
  - 训练参数和系统信息展示面板
  - 增强的日志终端（自动滚动控制）
  - 自动刷新机制（运行中任务每 10 秒刷新）
  - WebSocket 实时日志流

- **训练超参数管理优化**
  - TrainingJob 模型新增 `hyperparams` 字段
  - 支持任务级超参数覆盖能力级默认配置
  - 前端表单支持常用参数（epochs、batch、imgsz、lr0、device、pretrained）
  - 高级参数 JSON 编辑器（完整控制所有超参数）
  - 数据库迁移脚本（向后兼容）

### 修复 (Fixed)

- **能力删除级联失败** — 修复删除 AI 能力时关联数据未级联删除的问题
  - 在 Capability 模型的关系中添加 `cascade="all, delete-orphan"`
  - 自动删除关联的 TrainingJob、ModelVersion、AnnotationProject
  - 确保数据完整性和一致性

### 安全 (Security)

- 模型文件完整性验证（SHA256 checksum）
- CI/CD 安全扫描（Trivy 漏洞检测）

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
