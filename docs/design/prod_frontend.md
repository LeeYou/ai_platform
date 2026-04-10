# 生产服务 Web 管理前端设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.1 | 2026-04-10**

---

## 1. 概述

生产服务（prod）除了提供 REST API 推理接口外，还需要提供一个内置的 Web 管理页面，用于：

1. **API 接口测试**：选择 AI 能力模块，上传测试图片，直观查看推理结果
2. **服务状态监控**：查看服务健康状态、各能力加载状态、License 状态
3. **AI 能力编排管理**：可视化创建和管理 AI 能力编排 Pipeline
4. **Pipeline 测试**：测试编排流水线的执行效果

### 1.1 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 前端框架 | Vue 3 + Vite | 与其他子系统保持一致 |
| UI 组件库 | Element Plus | 与其他子系统保持一致 |
| HTTP 客户端 | axios | 与其他子系统保持一致 |
| 路由 | Vue Router | SPA 路由 |
| 服务端 | nginx | 静态文件服务 + 反向代理 |

### 1.2 架构方式

生产容器采用两阶段构建（Node.js 编译前端 + CUDA Runtime 运行后端），单 uvicorn 进程同时提供 API 和前端静态文件：

```
uvicorn (port 8080)
  ├── /api/  → FastAPI 路由（推理、健康检查、Pipeline、管理接口）
  └── /      → FastAPI StaticFiles（前端静态文件 /app/prod/frontend/dist/）
```

Docker Compose 中宿主机端口映射：`8080 → 容器 8080`

---

## 2. 页面规划

### 2.1 导航结构

```
├── 仪表盘 (Dashboard)
├── API 测试 (API Test)
│   ├── 单能力测试
│   └── 结果历史
├── AI 编排 (Pipelines)
│   ├── 编排列表
│   ├── 新建编排
│   └── 编排测试
├── 服务状态 (Status)
│   ├── 能力列表
│   └── License 信息
└── 系统管理 (Admin)
    └── 热重载
```

### 2.2 仪表盘页面 (Dashboard)

- **服务状态卡片**：healthy/unhealthy 状态指示
- **能力统计**：已加载能力数 / 总能力数
- **License 状态**：有效期、剩余天数、授权能力列表
- **GPU 状态**：GPU 可用性、后端类型
- **快捷操作**：API 测试、编排管理入口

### 2.3 API 测试页面

#### 单能力测试

1. **能力选择下拉框**：从 `/api/v1/capabilities` 动态加载可用能力列表
2. **图片上传区域**：拖拽或点击上传测试图片
3. **参数配置**（可选）：JSON 编辑器，配置 threshold 等推理参数
4. **执行按钮**：调用 `/api/v1/infer/{capability}` 执行推理
5. **结果展示区域**：
   - 原始 JSON 响应
   - 推理耗时统计
   - 可视化结果（如人脸框、文字识别结果等叠加在图片上）

### 2.4 AI 编排管理页面

#### 编排列表

- **Pipeline 卡片/表格**：显示 pipeline_id、名称、描述、步骤数、启用状态
- **操作按钮**：编辑、删除、启用/禁用、测试
- **新建按钮**：跳转到新建编排页面

#### 新建/编辑编排

- **基本信息**：pipeline_id、名称、描述
- **步骤编辑器**：
  - 添加步骤按钮
  - 每个步骤卡片：选择 AI 能力、配置 options、设置 condition、配置 on_failure
  - 步骤拖拽排序
  - 输入/输出映射配置
- **最终输出配置**：final_output 表达式编辑
- **验证按钮**：调用 validate 接口验证配置
- **保存按钮**：保存 Pipeline 配置

#### 编排测试

- **Pipeline 选择**：下拉选择要测试的 Pipeline
- **图片上传**：上传测试数据
- **执行按钮**：执行 Pipeline
- **结果展示**：
  - 流水线步骤可视化（每步状态、耗时）
  - 每步详细结果
  - 最终输出结果
  - 总耗时统计

### 2.5 服务状态页面

#### 能力列表

- **表格**：能力名称、状态（loaded/unavailable）、模型版本、来源（mount/builtin）
- **状态指示灯**：绿色（loaded）、红色（unavailable）

#### License 信息

- **License 状态**：valid/expired/invalid
- **有效期**：起止日期
- **剩余天数**
- **授权能力列表**

### 2.6 系统管理页面

- **热重载**：选择能力执行热重载（需 Admin Token 认证）
- **全量重载**：重载所有能力

---

## 3. API 依赖

前端页面依赖以下后端 API：

| 页面 | API | 说明 |
|------|-----|------|
| Dashboard | GET /api/v1/health | 服务状态 |
| Dashboard | GET /api/v1/capabilities | 能力列表 |
| Dashboard | GET /api/v1/license | License 状态 |
| API 测试 | GET /api/v1/capabilities | 能力列表 |
| API 测试 | POST /api/v1/infer/{cap} | 执行推理 |
| 编排列表 | GET /api/v1/pipelines | 列出 Pipelines |
| 编排编辑 | POST/PUT /api/v1/pipelines | 创建/更新 |
| 编排编辑 | POST /api/v1/pipelines/{id}/validate | 验证 |
| 编排测试 | POST /api/v1/pipeline/{id}/run | 执行 Pipeline |
| 热重载 | POST /api/v1/admin/reload | 重载 |

---

## 4. 前端目录结构

```
prod/frontend/
├── package.json
├── vite.config.js
├── index.html
├── public/
└── src/
    ├── main.js
    ├── App.vue
    ├── router/
    │   └── index.js
    ├── api/
    │   └── index.js     # axios 实例 + extractErrorMessage
    ├── views/
    │   ├── Dashboard.vue
    │   ├── ApiTest.vue
    │   ├── Pipelines.vue
    │   ├── PipelineEdit.vue
    │   ├── PipelineTest.vue
    │   ├── Status.vue
    │   └── Admin.vue
    └── components/
        └── NavMenu.vue
```

---

## 5. 容器部署变更

### 5.1 Dockerfile 更新

生产容器 Dockerfile 采用两阶段构建：

1. Stage 1（node:18-slim）：编译前端 Vue 项目，生成 `/app/prod/frontend/dist/`
2. Stage 2（nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04）：Python 运行时 + uvicorn，通过 FastAPI StaticFiles 托管前端产物

### 5.2 docker-compose.prod.yml 更新

增加 Pipeline 目录挂载：

```yaml
volumes:
  - /data/ai_platform/pipelines:/mnt/ai_platform/pipelines
```

---

## 6. 与新增 AI 能力的关联

当新增一个 AI 能力模块时，生产前端需要自动适配：

1. **API 测试页**：新能力自动出现在能力选择下拉框中（从 capabilities API 动态加载）
2. **编排管理**：新能力自动出现在步骤编辑器的能力选择列表中
3. **状态页面**：新能力自动出现在能力列表中

> **无需手动更新前端代码**：所有能力列表均通过 API 动态获取。

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
