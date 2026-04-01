# AI 能力编排子系统设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-29**

---

## 1. 概述

AI 能力编排子系统为生产推理服务提供多能力串行/并行组合调用的能力。某些业务场景需要将多个 AI 能力按照特定顺序和逻辑组合在一起，形成一个完整的推理流水线（Pipeline）。

### 1.1 典型业务场景

| 场景 | 编排流程 | 说明 |
|------|---------|------|
| 指令活体检测 | face_detect → face_liveness_action → recapture_detect | 先检测人脸，再做活体动作检测，最后做翻拍攻击检测 |
| 静默活体检测 | face_detect → face_liveness_silent → recapture_detect | 先检测人脸，再做静默活体检测，最后做翻拍攻击检测 |
| 身份证识别+人脸比对 | id_card_ocr → face_detect → face_verify | 识别身份证照片，检测人脸，比对证件照与现场照 |
| 合同审核流水线 | doc_classify → contract_extract → contract_seal_detect → contract_sign_locate | 分类→抽取→印章检测→签名定位 |
| 内容安全审核 | image_classify → content_compliance → sensitive_detect | 图片分类→合规检测→敏感内容检测 |

### 1.2 设计原则

1. **配置化编排**：通过 JSON/YAML 配置定义流水线，无需修改代码
2. **条件分支**：支持根据上一步结果决定是否继续（如人脸检测失败则终止）
3. **结果透传**：上一步输出可作为下一步输入或参数
4. **统一入口**：编排后的流水线对外暴露为一个统一接口
5. **Web 管理**：在生产镜像的管理页面中提供可视化编排配置

---

## 2. 数据模型

### 2.1 Pipeline 定义

```json
{
  "pipeline_id": "active_liveness_check",
  "name": "指令活体检测",
  "description": "人脸检测 + 活体动作验证 + 翻拍攻击检测",
  "version": "1.0.0",
  "enabled": true,
  "steps": [
    {
      "step_id": "detect_face",
      "capability": "face_detect",
      "options": { "threshold": 0.6 },
      "on_failure": "abort",
      "output_mapping": {
        "face_bbox": "$.result.detections[0].bbox",
        "face_confidence": "$.result.detections[0].confidence"
      }
    },
    {
      "step_id": "check_liveness",
      "capability": "face_liveness_action",
      "input_from": {
        "face_region": "${detect_face.face_bbox}"
      },
      "options": {},
      "on_failure": "abort",
      "condition": "${detect_face.face_confidence} >= 0.5",
      "output_mapping": {
        "is_live": "$.result.is_live",
        "liveness_score": "$.result.score"
      }
    },
    {
      "step_id": "check_recapture",
      "capability": "recapture_detect",
      "options": { "threshold": 0.5 },
      "on_failure": "abort",
      "condition": "${check_liveness.is_live} == true",
      "output_mapping": {
        "is_recaptured": "$.result.is_recaptured",
        "recapture_score": "$.result.score"
      }
    }
  ],
  "final_output": {
    "face_detected": "${detect_face.face_confidence} >= 0.5",
    "is_live": "${check_liveness.is_live}",
    "liveness_score": "${check_liveness.liveness_score}",
    "is_recaptured": "${check_recapture.is_recaptured}",
    "recapture_score": "${check_recapture.recapture_score}",
    "overall_pass": "${check_liveness.is_live} == true && ${check_recapture.is_recaptured} == false"
  }
}
```

### 2.2 Pipeline 存储

编排配置以 JSON 文件形式存储在宿主机挂载目录：

```
/data/ai_platform/pipelines/
├── active_liveness_check.json
├── silent_liveness_check.json
├── id_verify_pipeline.json
└── contract_review_pipeline.json
```

容器内映射路径：`/mnt/ai_platform/pipelines/`

---

## 3. REST API 设计

### 3.1 管理接口

| 接口 | 方法 | 说明 | 鉴权 |
|------|------|------|------|
| `/api/v1/pipelines` | GET | 列出所有编排 Pipeline | 无 |
| `/api/v1/pipelines` | POST | 创建新 Pipeline | Admin Token |
| `/api/v1/pipelines/{pipeline_id}` | GET | 获取 Pipeline 详情 | 无 |
| `/api/v1/pipelines/{pipeline_id}` | PUT | 更新 Pipeline 配置 | Admin Token |
| `/api/v1/pipelines/{pipeline_id}` | DELETE | 删除 Pipeline | Admin Token |
| `/api/v1/pipelines/{pipeline_id}/validate` | POST | 验证 Pipeline 配置有效性 | Admin Token |

### 3.2 执行接口

| 接口 | 方法 | 说明 | 鉴权 |
|------|------|------|------|
| `/api/v1/pipeline/{pipeline_id}/run` | POST | 执行编排流水线 | License |

### 3.3 执行请求示例

```
POST /api/v1/pipeline/active_liveness_check/run
Content-Type: multipart/form-data

image: <binary image file>
options: {"face_detect": {"threshold": 0.7}}  # 可选，覆盖步骤默认参数
```

### 3.4 执行响应示例

```json
{
  "code": 0,
  "message": "success",
  "pipeline_id": "active_liveness_check",
  "pipeline_version": "1.0.0",
  "total_time_ms": 45.2,
  "steps": [
    {
      "step_id": "detect_face",
      "capability": "face_detect",
      "status": "success",
      "time_ms": 12.5,
      "result": { "detections": [...] }
    },
    {
      "step_id": "check_liveness",
      "capability": "face_liveness_action",
      "status": "success",
      "time_ms": 18.3,
      "result": { "is_live": true, "score": 0.95 }
    },
    {
      "step_id": "check_recapture",
      "capability": "recapture_detect",
      "status": "success",
      "time_ms": 14.4,
      "result": { "is_recaptured": false, "score": 0.12 }
    }
  ],
  "final_result": {
    "face_detected": true,
    "is_live": true,
    "liveness_score": 0.95,
    "is_recaptured": false,
    "recapture_score": 0.12,
    "overall_pass": true
  }
}
```

---

## 4. Pipeline 执行引擎

### 4.1 执行流程

```
客户端请求 → 解析 Pipeline 配置
  → 遍历 steps：
     ├── 评估 condition 表达式
     │     ├── 条件不满足 → 跳过该步骤
     │     └── 条件满足 → 继续
     ├── 组装输入（原始输入 + input_from 引用上游输出）
     ├── 调用对应 capability 推理
     ├── 评估 output_mapping 提取结果
     └── 检查 on_failure 策略
           ├── "abort"  → 立即终止，返回错误
           ├── "skip"   → 标记失败，继续下一步
           └── "default" → 使用默认值，继续下一步
  → 所有步骤完成
  → 评估 final_output 表达式
  → 返回完整结果
```

### 4.2 表达式引擎

支持简单的变量引用和比较表达式：

- **变量引用**：`${step_id.key}` 引用上游步骤的 output_mapping 值
- **JSONPath**：`$.result.detections[0].bbox` 从步骤原始结果中提取数据
- **比较运算**：`>=`, `<=`, `==`, `!=`, `>`, `<`
- **逻辑运算**：`&&`, `||`
- **字面值**：`true`, `false`, 数字, 字符串

### 4.3 错误处理

| 情况 | 处理策略 |
|------|---------|
| 步骤 capability 不存在 | Pipeline validate 时报错 |
| 步骤 capability 未授权 | 运行时返回 4004 错误 |
| 步骤推理失败 | 根据 on_failure 策略处理 |
| condition 表达式错误 | 运行时返回 1001 参数错误 |
| Pipeline 定义格式错误 | 创建/更新时返回 400 |

---

## 5. Web 管理界面

生产镜像的管理 Web 页面中提供 AI 编排管理功能：

### 5.1 编排列表页

- 显示所有已配置的 Pipeline（名称、描述、步骤数、状态）
- 支持新建、编辑、删除、启用/禁用操作
- 每个 Pipeline 显示其包含的 AI 能力步骤流程图

### 5.2 编排编辑页

- 可视化步骤配置：添加/删除/重排步骤
- 每个步骤可选择 AI 能力（从已加载能力列表中选择）
- 配置步骤参数：options、condition、on_failure 策略
- 配置输入/输出映射
- 实时验证 Pipeline 配置有效性

### 5.3 编排测试页

- 上传测试图片/数据
- 执行指定 Pipeline
- 可视化展示每个步骤的执行结果和耗时
- 整体结果展示

---

## 6. 与其他子系统的关联

### 6.1 新增 AI 能力时的更新清单

当新增一个 AI 能力模块时，AI 编排子系统需要同步更新：

1. 新能力自动出现在编排步骤的能力选择列表中（动态读取已加载能力）
2. 如有涉及该新能力的预定义 Pipeline，需要在 `pipelines/` 目录下创建对应配置
3. 更新编排测试页面的测试数据（如有需要）

### 6.2 与 License 系统的关系

- Pipeline 执行时，每个步骤的 capability 都需要通过 License 校验
- 如果 Pipeline 中某个步骤的 capability 未授权，该步骤会返回 4004 错误
- Pipeline 整体执行不需要额外授权，授权控制在单个 capability 层面

---

## 7. 目录规范

```
/data/ai_platform/
├── pipelines/                    # Pipeline 编排配置
│   ├── active_liveness_check.json
│   ├── silent_liveness_check.json
│   └── ...
```

容器挂载：

```yaml
volumes:
  - /data/ai_platform/pipelines:/mnt/ai_platform/pipelines
```

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
