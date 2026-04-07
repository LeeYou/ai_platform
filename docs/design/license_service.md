# 授权子系统设计

**北京爱知之星科技股份有限公司 (Agile Star)**  
**文档版本：v1.0 | 2026-03-27**

---

## 1. 概述

授权子系统是独立的授权管理平台，负责为客户生成、管理和校验 AI 能力使用授权。授权文件使用 RSA-2048 + SHA256 数字签名，支持机器硬件绑定、试用期限和长期授权等模式。

---

## 2. 容器设计

| 属性 | 值 |
|------|-----|
| 镜像名 | `agilestar/ai-license-mgr:latest` |
| 基础镜像 | `python:3.11-slim` |
| 服务端口 | 8003（Web 管理界面） |
| 后端框架 | Python FastAPI |
| 前端框架 | Vue3 + Element Plus |
| 数据库 | SQLite（单机）/ PostgreSQL（多实例） |
| 签名算法 | RSA-2048 + SHA256 |

---

## 3. License 文件格式

### 3.1 文件结构

License 文件是一个 JSON 结构，使用 RSA 私钥对全部字段做数字签名，签名附在文件末尾。

```json
{
  "license_id": "LS-20260327-0001",
  "customer_id": "CUST-001",
  "customer_name": "某客户公司",
  "license_type": "commercial",
  "capabilities": ["face_detect", "handwriting_reco"],
  "machine_fingerprint": "sha256:a1b2c3d4e5f6...",
  "valid_from": "2026-04-01T00:00:00Z",
  "valid_until": "2026-10-01T00:00:00Z",
  "version_constraint": ">=1.0.0,<2.0.0",
  "max_instances": 4,
  "issuer": "agilestar.cn",
  "issued_at": "2026-03-27T07:00:00Z",
  "signature": "BASE64(RSA-SHA256-SIGN(上述全部字段的规范化JSON字节))"
}
```

### 3.2 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `license_id` | string | 唯一授权编号，格式 `LS-YYYYMMDD-NNNN` |
| `customer_id` | string | 客户唯一标识 |
| `customer_name` | string | 客户名称（含于签名中） |
| `license_type` | enum | `trial`（试用）/ `commercial`（商业）/ `permanent`（永久） |
| `capabilities` | array | 授权的能力列表，`["*"]` 表示全部能力 |
| `machine_fingerprint` | string | 机器指纹哈希，`null` 表示不绑定机器 |
| `valid_from` | datetime | 生效时间（UTC） |
| `valid_until` | datetime | 到期时间（UTC），`null` 表示永久有效 |
| `version_constraint` | string | 允许使用的 SO 版本范围（semver 语义） |
| `max_instances` | int | 允许的最大并发推理实例数 |
| `signature` | string | Base64 编码的 RSA-SHA256 数字签名 |

### 3.3 授权类型

| 类型 | valid_until | 典型场景 |
|------|------------|---------|
| `trial` | 设置到期日期（如 3 个月后） | 客户试用 |
| `commercial` | 设置到期日期（如 1 年后） | 年度商业授权 |
| `permanent` | `null` | 买断式永久授权 |

---

## 4. 机器指纹生成规则

为防止单一硬件 ID 失效导致授权失效，机器指纹由多个硬件特征组合哈希生成：

```
fingerprint = SHA256(
    CPU序列号 +
    主板序列号 +
    第一块网卡 MAC 地址 +
    （可选）主磁盘序列号
)
```

### 指纹采集工具

提供跨平台命令行工具 `license_tool`（C++ 实现，随交付包附带）：

```bash
# 采集当前机器指纹（交付给授权管理员生成 License）
./license_tool fingerprint

# 输出示例：
# Machine Fingerprint: sha256:a1b2c3d4e5f6789abcdef0123456789
# CPU S/N:   BFEBFBFF000906EA
# Board S/N: V1.0
# NIC MAC:   AA:BB:CC:DD:EE:FF
```

---

## 5. SO 单层校验与一致性策略

- 生产环境的运行时授权准入只在 Runtime / SO 层执行，Web 层不再重复做授权判定。
- Web 层仅保留 `/health`、`/license/status` 等状态展示接口，以及对 Runtime 错误码/消息的透传。
- SO 侧校验内容至少包括：签名有效性、有效期、能力范围、机器指纹匹配（如配置）、版本约束、实例数上限。
- 授权镜像侧不再维护独立的运行时准入逻辑；其签名与校验协议必须与 SO 侧保持同一 canonical JSON、同一时间语义、同一错误语义。
- 一致性通过同一组 golden license 回归样本验证，确保授权镜像与 SO 对同一授权文件得出完全一致的结论。

---

## 6. 授权管理 Web 系统

### 6.1 功能模块

#### 客户管理

- 创建/编辑/删除客户信息（客户 ID、名称、联系人、邮箱）
- 查看客户授权列表

#### 授权生成

1. 选择客户
2. 选择授权类型和有效期
3. 勾选授权的 AI 能力范围
4. 输入目标机器指纹（由 `license_tool fingerprint` 采集）
5. 设置并发实例数上限
6. 点击生成 → 系统使用私钥签名 → 输出 `license.bin`
7. 下载 License 文件，随交付包一起交付给客户

#### 授权列表

| 列表字段 | 说明 |
|---------|------|
| 授权编号 | `LS-YYYYMMDD-NNNN` |
| 客户名称 | |
| 授权类型 | 试用/商业/永久 |
| 能力范围 | 逗号分隔的能力标识 |
| 生效时间 | |
| 到期时间 | 永久则显示"永久" |
| 剩余天数 | 已过期则红色高亮 |
| 状态 | 有效/已过期/已吊销 |
| 操作 | 延期/吊销/重新下载 |

#### 到期提醒

- 系统每日自动检查所有有效授权的到期时间
- 到期前 30 天：界面橙色警告
- 到期前 15 天：界面红色警告 + 可选邮件提醒
- 到期前 7 天：每日提醒
- 到期当天：系统通知

#### 授权延期

1. 选择要延期的授权记录
2. 设置新的到期时间
3. 系统重新签名生成新 License 文件
4. 下载新 License 文件交付客户（替换原文件）

#### 授权吊销

- 将授权标记为吊销状态
- 吊销列表可发布为 CRL（证书吊销列表）
- 生产容器可定期拉取 CRL（可选功能）

#### 密钥管理

- RSA 密钥对管理（私钥离线存储，公钥内置于 SO）
- 支持密钥轮换（生成新密钥对，重新颁发 License）
- 私钥**绝不**出现在生产容器或交付物中

---

## 7. License 文件部署规范

### 客户侧部署

```
# 将 license.bin 放入宿主机挂载目录
/data/ai_platform/licenses/<customer_id>/license.bin

# 生产容器挂载后自动加载
/mnt/ai_platform/licenses/<customer_id>/license.bin
```

### 更新 License（延期后）

```bash
# 1. 停止旧 license.bin
# 2. 替换为新 license.bin
cp new_license.bin /data/ai_platform/licenses/<customer_id>/license.bin

# 3. 生产容器自动检测（60 秒轮询）或调用 reload 接口立即生效
curl -X POST http://localhost:8080/api/v1/admin/reload \
     -H "Authorization: Bearer <admin_token>"
```

---

## 8. 授权校验流程图

```
服务启动
  ↓
读取 License 文件
  ↓
使用内置公钥验证 RSA 签名
  ├─ 签名无效 → 启动失败，记录错误日志
  └─ 签名有效 ↓
        ↓
检查机器指纹（若 License 绑定了机器）
  ├─ 不匹配 → 启动失败
  └─ 匹配 ↓
        ↓
检查有效期
  ├─ 未生效 → 推理不可用，状态接口可用
  ├─ 已过期 → 推理不可用，状态接口可用
  └─ 有效 ↓
        ↓
检查能力范围
  → 仅加载 License 授权范围内的能力
        ↓
服务正常运行，推理接口可用
```

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
