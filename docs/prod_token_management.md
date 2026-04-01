# 生产服务管理令牌 (Production Admin Token) 使用指南

> **版本:** 1.0 | **日期:** 2026-04-01

## 1. 概述

生产服务管理令牌用于保护生产推理服务 (ai-prod) 的敏感管理接口，包括：
- 热重载 API (`/api/v1/admin/reload`)
- 能力级重载 (`/api/v1/admin/reload/{capability}`)

## 2. 安全设计

### 2.1 核心特性

- **密码学安全生成**：使用 Python `secrets.token_hex(32)` 生成 256 位随机令牌
- **仅显示一次**：明文令牌仅在创建时显示一次，之后无法查看
- **哈希存储**：数据库仅存储 SHA-256 哈希值，不存储明文
- **时序攻击防护**：使用 `hmac.compare_digest()` 进行安全比较
- **审计日志**：记录令牌使用次数和最后使用时间
- **生命周期管理**：支持启用/停用、设置过期时间

### 2.2 安全优势

相比简单的环境变量配置：
- ✅ 统一管理，可视化操作
- ✅ 支持多环境（生产/预发布/测试）
- ✅ 可追踪令牌使用情况
- ✅ 支持定期轮换和失效
- ✅ 安全的哈希存储，防止泄漏

## 3. 使用步骤

### 3.1 生成新令牌

1. 访问授权管理服务：`http://<IP>:8003/#/prod-tokens`
2. 点击「生成新令牌」按钮
3. 填写表单：
   - **令牌名称**（必填）：如 `prod-token-2026`
   - **环境标识**（可选）：`production` / `staging` / `test`
   - **创建人**（可选）：操作员姓名
   - **过期时间**（可选）：留空表示永不过期
4. 点击「生成令牌」
5. **立即复制保存明文令牌**（仅此一次机会！）

### 3.2 配置生产服务

将生成的令牌配置到生产环境：

**方法 1：环境变量文件**
```bash
# 在 deploy/.env.prod 或类似文件中
echo "AI_ADMIN_TOKEN=<生成的令牌>" >> .env.prod
```

**方法 2：docker-compose.prod.yml**
```yaml
services:
  prod:
    environment:
      - AI_ADMIN_TOKEN=${AI_ADMIN_TOKEN}
```

**方法 3：直接在 docker run 中指定**
```bash
docker run -d \
  --name ai-prod \
  -e AI_ADMIN_TOKEN="<生成的令牌>" \
  ...
```

### 3.3 使用令牌调用管理接口

```bash
# 热重载所有能力
curl -X POST http://localhost:8080/api/v1/admin/reload \
  -H "Authorization: Bearer <你的令牌>"

# 重载单个能力
curl -X POST http://localhost:8080/api/v1/admin/reload/face_detect \
  -H "Authorization: Bearer <你的令牌>"
```

### 3.4 令牌管理操作

**停用令牌**：
- 在列表中点击「停用」按钮
- 已停用的令牌无法用于认证，但保留在数据库中

**启用令牌**：
- 点击「启用」按钮恢复已停用的令牌

**删除令牌**：
- 点击「删除」按钮永久删除令牌
- ⚠️ 此操作不可恢复

## 4. 令牌轮换建议

### 4.1 轮换周期

| 环境 | 推荐轮换周期 |
|------|------------|
| 生产环境 | 90 天 |
| 预发布环境 | 60 天 |
| 测试环境 | 30 天 |

### 4.2 轮换流程

1. 生成新令牌（新名称，如 `prod-token-2026-Q2`）
2. 更新生产服务配置为新令牌
3. 重启生产服务：`docker compose -f docker-compose.prod.yml restart`
4. 验证新令牌可用
5. 停用旧令牌（而非删除，保留审计记录）
6. 7 天后确认无问题，删除旧令牌

## 5. 故障排查

### 5.1 认证失败 (401 Unauthorized)

**问题**：调用管理接口返回 401

**排查步骤**：
1. 检查令牌是否正确复制（无多余空格或换行）
2. 确认 Header 格式：`Authorization: Bearer <token>`
3. 在管理页面检查令牌状态是否为「启用」
4. 检查令牌是否已过期
5. 查看生产服务日志确认令牌验证细节

### 5.2 令牌明文丢失

**问题**：忘记保存令牌明文

**解决方案**：
- 明文令牌无法找回（这是设计特性）
- 停用或删除旧令牌
- 生成新令牌并重新配置

### 5.3 数据库迁移

**问题**：启动授权服务后没有 `prod_admin_tokens` 表

**解决方案**：
```python
# license/backend/main.py 中的 lifespan 会自动创建表
# 如果没有自动创建，手动触发：
from database import Base, engine
Base.metadata.create_all(bind=engine)
```

## 6. API 参考

### 6.1 列出所有令牌
```http
GET /api/v1/prod-tokens
```

**响应示例**：
```json
[
  {
    "id": 1,
    "token_name": "prod-token-2026",
    "token_hash": "a7f3c9e2...",
    "environment": "production",
    "created_at": "2026-04-01T10:00:00",
    "created_by": "张三",
    "expires_at": null,
    "is_active": true,
    "last_used_at": "2026-04-01T12:30:00",
    "usage_count": 15
  }
]
```

### 6.2 生成新令牌
```http
POST /api/v1/prod-tokens
Content-Type: application/json

{
  "token_name": "prod-token-2026",
  "environment": "production",
  "created_by": "张三",
  "expires_at": "2026-07-01T00:00:00"
}
```

**响应示例**：
```json
{
  "id": 1,
  "token_name": "prod-token-2026",
  "token_hash": "a7f3c9e2...",
  "environment": "production",
  "plaintext_token": "a7f3c9e2b1d8f4a6c3e9b2d7f1a5c8e3b6d9f2a4c7e1b5d8f3a6c9e2b7f4a1c8",
  ...
}
```

### 6.3 更新令牌状态
```http
PUT /api/v1/prod-tokens/{id}
Content-Type: application/json

{
  "is_active": false
}
```

### 6.4 删除令牌
```http
DELETE /api/v1/prod-tokens/{id}
```

## 7. 最佳实践

### 7.1 令牌命名规范

推荐格式：`{环境}-token-{年份}-{季度/月份}`

示例：
- `prod-token-2026-Q2`
- `staging-token-2026-04`
- `test-token-2026`

### 7.2 安全存储

生产环境令牌应存储在：
- ✅ 团队密码管理器（1Password、Bitwarden）
- ✅ 安全的配置管理系统（Vault、AWS Secrets Manager）
- ✅ 加密的环境变量文件（`.env.prod`，不提交到 Git）

❌ 不要：
- 硬编码在代码中
- 提交到 Git 仓库
- 通过邮件/聊天软件明文传输

### 7.3 权限控制

- 仅授权运维人员访问授权管理页面 `:8003`
- 生产环境令牌只允许必要人员知晓
- 定期审计令牌使用情况

## 8. 与现有系统集成

### 8.1 生产服务验证流程

生产服务 (`prod/web_service/main.py`) 当前的验证逻辑：
```python
ADMIN_TOKEN = os.getenv("AI_ADMIN_TOKEN", "changeme")

def _verify_admin(request: Request) -> None:
    import hmac
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")
```

### 8.2 可选：集中验证（未来扩展）

可选择让生产服务调用授权服务验证令牌：
```python
# prod/web_service/main.py 中修改验证逻辑
import requests

def _verify_admin(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()

    # 调用授权服务验证
    resp = requests.post(
        "http://license:8003/api/v1/prod-tokens/verify",
        json={"plaintext_token": token}
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Unauthorized")
```

优势：
- 集中管理，无需重启生产服务即可停用令牌
- 自动记录使用审计日志
- 支持过期时间自动失效

## 9. 附录

### 9.1 手动生成令牌（命令行）

如果需要在命令行生成令牌：
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 9.2 验证令牌哈希

验证已知明文令牌的哈希值：
```python
import hashlib
plaintext = "你的令牌明文"
hash_value = hashlib.sha256(plaintext.encode()).hexdigest()
print(hash_value)
```

### 9.3 数据库架构

```sql
CREATE TABLE prod_admin_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_name VARCHAR(100) UNIQUE NOT NULL,
    token_hash VARCHAR(128) NOT NULL,
    environment VARCHAR(50),
    created_at TIMESTAMP NOT NULL,
    created_by VARCHAR(100),
    expires_at TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    last_used_at TIMESTAMP,
    usage_count INTEGER NOT NULL DEFAULT 0
);
```

---

**文档维护者**：AI Platform Team
**最后更新**：2026-04-01
**版本历史**：v1.0 - 初始版本
