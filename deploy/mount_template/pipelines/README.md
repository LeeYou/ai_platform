# 预置 Pipeline 配置

本目录包含平台预置的 AI 能力编排流水线模板。

## 文件说明

| 文件 | 名称 | 描述 |
|------|------|------|
| `active_liveness_check.json` | 指令活体检测 | face_detect → face_liveness_action → recapture_detect |
| `silent_liveness_check.json` | 静默活体检测 | face_detect → face_liveness_silent → recapture_detect |

## 使用方法

1. 宿主机 `init_host_dirs.sh` 脚本会自动创建 `/data/ai_platform/pipelines/` 目录
2. 将本目录下的 JSON 文件复制到宿主机 `/data/ai_platform/pipelines/`
3. 生产容器启动后通过挂载自动加载这些 Pipeline 定义
4. 也可通过生产 Web 管理界面的"编排管理"页面在线创建/编辑 Pipeline

```bash
# 复制预置 Pipeline 到宿主机
sudo cp deploy/mount_template/pipelines/*.json /data/ai_platform/pipelines/
```

## 自定义 Pipeline

参照 JSON 格式创建新的 Pipeline 配置文件，放入 `/data/ai_platform/pipelines/` 即可。
也可通过 REST API 或 Web 管理界面创建。

### JSON 字段说明

- `pipeline_id`: 唯一标识符（建议用 snake_case）
- `name`: 显示名称
- `description`: 描述
- `enabled`: 是否启用
- `steps`: 步骤数组
  - `step_id`: 步骤标识
  - `capability`: 对应的 AI 能力名称
  - `params`: 传递给能力的额外参数
  - `condition`: 执行条件（引用上游步骤输出，如 `${detect_face.face_count} > 0`）
  - `on_failure`: 失败策略 — `abort`（中止）/ `skip`（跳过）/ `default`（使用默认值）
- `output_mapping`: 最终输出映射（引用各步骤结果）
