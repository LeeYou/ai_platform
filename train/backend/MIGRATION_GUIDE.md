# 训练管理系统更新说明

## 更新日期：2026-03-31

### 问题修复

#### 1. AI能力删除失败问题

**问题描述：**
在Web页面删除AI能力时报错，因为存在关联的训练任务、模型版本和标注项目。

**解决方案：**
- 在 `Capability` 模型中为 `jobs`、`model_versions`、`annotation_projects` 关系添加了级联删除
- 删除能力时会自动删除所有关联的训练任务、模型版本和标注项目

**影响：**
- 删除AI能力前请确认是否需要保留相关数据
- 建议在删除前导出重要的模型版本和标注数据

#### 2. 训练参数输入缺失问题

**问题描述：**
Web界面创建训练任务时，只能选择能力和版本号，无法填写操作手册中描述的训练参数（epochs、batch、imgsz、lr0等）。

**解决方案：**
- 在 `TrainingJob` 模型中添加 `hyperparams` 字段用于存储任务级参数
- 更新前端 `Jobs.vue`，添加完整的参数输入表单：
  - 基础参数：训练轮次、批大小、图像尺寸、学习率、GPU设备、基础模型
  - 高级参数：支持JSON格式自定义参数
  - 显示能力默认参数供参考
- 后端自动合并能力默认参数和任务特定参数

**使用方式：**
1. 点击"新建训练任务"
2. 选择AI能力和版本号
3. （可选）填写训练参数，留空则使用能力默认值
4. （可选）展开"高级参数"填写JSON格式的自定义参数
5. 提交任务

**参数优先级：**
```
高级参数(JSON) > 基础参数表单 > 能力默认参数
```

### 数据库变更

#### 新增字段

- `training_jobs.hyperparams` (TEXT, NOT NULL, DEFAULT '{}')

#### 迁移方式

**方式一：自动迁移（推荐）**
新部署或重启服务时，SQLAlchemy会自动创建新字段（仅对新建的数据库）。

**方式二：手动迁移（现有数据库）**
```bash
cd /app
python migrate_add_job_hyperparams.py
```

迁移脚本会检查字段是否存在，避免重复执行。

### API变更

#### TrainingJobCreate Schema

**之前：**
```json
{
  "capability_id": 1,
  "version": "1.0.0"
}
```

**现在：**
```json
{
  "capability_id": 1,
  "version": "1.0.0",
  "hyperparams": "{\"epochs\": 100, \"batch\": 16, \"imgsz\": 640}"  // 可选
}
```

#### TrainingJobOut Schema

新增返回字段：
- `hyperparams`: 任务的训练参数（已解析为JSON对象）

### 前端变更

#### Jobs.vue 新建训练任务对话框

**新增表单项：**
- 训练轮次 (epochs)
- 批大小 (batch)
- 图像尺寸 (imgsz)
- 学习率 (lr0)
- GPU设备 (device)
- 基础模型 (pretrained)
- 高级参数（可折叠，JSON格式）

**新增功能：**
- 实时JSON格式验证
- 显示能力默认参数作为参考
- 参数说明提示

### 兼容性说明

- ✅ 向后兼容：不填写 `hyperparams` 时使用能力默认参数
- ✅ API兼容：旧的请求格式仍然有效
- ⚠️ 数据库兼容：需要运行迁移脚本添加 `hyperparams` 字段

### 测试建议

1. **能力删除测试**
   - 创建一个测试能力
   - 为该能力创建训练任务
   - 删除能力，验证相关数据被级联删除

2. **参数传递测试**
   - 创建训练任务并填写参数
   - 查看训练日志，验证参数正确传递给训练脚本
   - 验证参数合并逻辑（能力默认 + 任务覆盖）

3. **迁移脚本测试**
   - 在现有数据库上运行迁移脚本
   - 验证字段添加成功
   - 验证现有数据不受影响

### 相关文件

**后端：**
- `train/backend/models.py` - 数据模型更新
- `train/backend/schemas.py` - API Schema更新
- `train/backend/crud.py` - CRUD逻辑更新
- `train/backend/routers/jobs.py` - 参数合并逻辑
- `train/backend/migrate_add_job_hyperparams.py` - 迁移脚本

**前端：**
- `train/frontend/src/views/Jobs.vue` - 新建训练任务UI

### 后续建议

1. 考虑添加参数模板功能，保存常用参数配置
2. 在任务列表中显示关键参数（epochs、batch等）
3. 添加参数历史记录，方便对比不同参数的训练效果
4. 考虑添加参数范围验证（如batch不能超过GPU内存限制）
