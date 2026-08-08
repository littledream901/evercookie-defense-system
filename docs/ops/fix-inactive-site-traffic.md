# 修复已删除站点仍产生访问日志的问题

## 问题现象

已在防御系统后台删除的 Cloudflare Worker 站点，访问数据仍然出现在系统访问日志中。

## 根本原因

### 问题链路

```
1. 后台删除站点
   ↓
2. 系统删除 MySQL 记录 + Redis 映射（fangyu:app_keys:{site_key}）
   ↓
3. 但 Cloudflare Workers 代码仍在边缘节点运行
   ↓
4. Worker 持有旧的 site_key 和 site_secret（硬编码在环境变量）
   ↓
5. 真实用户访问 → Worker 发送请求到 Gateway
   ↓
6. Gateway 的 AppKeyResolver 有 60s 本地缓存 + Redis 可能有残留
   ↓
7. 请求通过鉴权 → 决策写入 ClickHouse → 显示在访问日志
```

### 技术细节

1. **Gateway 不验证站点激活状态**
   - `AppKeyResolver.resolve_credential` 只检查 Redis 中是否有映射
   - 没有回查站点的 `is_active` 状态
   - 旧代码参考：[app_key.py:105-123](../gateway-api/src/interfaces/http/middleware/app_key.py)

2. **本地缓存延迟**
   - Gateway 的 `AppKeyResolver` 有 60 秒本地进程缓存
   - 删除 Redis 键后，缓存期内仍可通过鉴权

3. **CF Worker 未清理**
   - Cloudflare Workers 是独立部署的边缘代码
   - 后台删除站点不会自动停用 Worker

## 解决方案

### 方案 1：立即清理 Cloudflare Worker（最快生效）

**适用场景**：快速止血，阻止旧站点继续产生流量

**操作步骤**：

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com)
2. 选择对应域名
3. 进入 **Workers Routes** 或 **Workers & Pages**
4. 找到绑定旧站点的 Worker
5. **停用（Disable）** 或 **删除（Delete）** 该 Worker

**生效时间**：立即生效（Cloudflare 边缘节点 1-2 分钟内同步）

---

### 方案 2：系统增强 - Gateway 验证站点状态（根治）

**适用场景**：从系统层面防止已停用/删除站点继续通过鉴权

#### 2.1 代码变更说明

本次修改已完成以下文件更改：

1. **admin-api/src/infrastructure/cache/app_key_sync.py**
   - `bind()` 方法增加 `is_active` 参数
   - Redis 映射 JSON 增加 `is_active` 字段

2. **gateway-api/src/interfaces/http/middleware/app_key.py**
   - `AppCredential` 增加 `is_active` 字段
   - `_parse()` 解析 Redis 值时读取 `is_active`（旧数据默认 `True`）
   - `AppKeyEnforcementMiddleware.dispatch()` 验证 `is_active`，停用站点返回 401
   - `require_app_key()` 兜底路径也增加状态验证

3. **admin-api/src/application/services/site_service.py**
   - `_sync_bind()` 同步站点到 Redis 时传递 `is_active` 状态

#### 2.2 部署步骤

##### 步骤 1：备份现有 Redis 数据（可选但推荐）

```bash
# 在 Redis 容器内执行
docker exec -it fangyu-redis redis-cli

# 导出所有 app_keys 映射
redis-cli --scan --pattern "fangyu:app_keys:*" | \
  xargs -I {} sh -c 'echo "{}"; redis-cli GET "{}"' > /backup/app_keys_backup.txt
```

##### 步骤 2：迁移现有 Redis 数据

```bash
# 在项目根目录执行
cd /path/to/Evercookie-Defense-System-V2

# 进入 admin-api 容器（或本地配置相同环境变量）
docker exec -it fangyu-admin-api bash

# 执行迁移脚本
python /app/scripts/migrate_redis_add_is_active.py
```

**迁移脚本功能**：
- 扫描所有 `fangyu:app_keys:*` 键
- 从数据库读取站点的 `is_active` 状态
- 更新 Redis JSON，增加 `is_active` 字段
- 自动备份原始值到 `fangyu:app_keys_backup:*`（TTL 24小时）
- 支持幂等执行，已迁移的键自动跳过

**预期输出**：
```
[INFO] migration_start
[INFO] fetching_site_status
[INFO] site_status_fetched total=15
[INFO] migrating_redis_keys
[INFO] key_migrated site_key=site_abc123 site_id=1 is_active=True
[INFO] key_migrated site_key=site_def456 site_id=2 is_active=False
...
[INFO] migration_completed success=15 skip=0 fail=0 total=15
```

##### 步骤 3：重新构建并部署镜像

```bash
# 构建新镜像
cd deploy
bash build.sh

# 推送镜像到仓库（如使用私有仓库）
docker push fangyu/admin-api:v2.0.5
docker push fangyu/gateway-api:v2.0.5

# 更新 .env.production 镜像版本
IMAGE_TAG=v2.0.5

# 重启服务
docker-compose down
docker-compose up -d
```

##### 步骤 4：验证功能

**方式 1：手动测试**

```bash
# 1. 停用一个测试站点
curl -X PUT https://defense.foxfingerlab.com/api/v2/sites/123 \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'

# 2. 使用该站点的 site_key 发送决策请求
curl -X POST https://gateway.foxfingerlab.com/v2/decide \
  -H "X-App-Key: site_xyz789" \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "clientIp": "1.2.3.4",
      "userAgent": "TestAgent",
      "visitUrl": "https://test.com"
    }
  }'

# 预期响应：
# HTTP 401
# {"code": "SITE_INACTIVE", "message": "站点已停用或删除"}
```

**方式 2：运行自动化测试**

```bash
# 进入 gateway-api 容器
docker exec -it fangyu-gateway bash

# 运行测试
pytest tests/gateway/test_site_active_validation.py -v
```

**预期输出**：
```
tests/gateway/test_site_active_validation.py::test_active_site_allowed PASSED
tests/gateway/test_site_active_validation.py::test_inactive_site_rejected PASSED
tests/gateway/test_site_active_validation.py::test_legacy_format_defaults_to_active PASSED
tests/gateway/test_site_active_validation.py::test_deleted_site_returns_none PASSED
tests/gateway/test_site_active_validation.py::test_inactive_site_e2e_rejection PASSED
```

#### 2.3 回滚方案

如果部署后发现问题，可快速回滚：

```bash
# 方式 1：回滚镜像版本
IMAGE_TAG=v2.0.4  # 修改为上一个稳定版本
docker-compose down
docker-compose up -d

# 方式 2：恢复 Redis 数据（如果迁移有问题）
# 迁移脚本已自动备份原始值到 fangyu:app_keys_backup:*
# 手动恢复单个键：
redis-cli GET fangyu:app_keys_backup:site_abc123 | \
  redis-cli -x SET fangyu:app_keys:site_abc123
```

## 新版本行为说明

### Redis 数据格式

**旧格式**（兼容读取）：
```json
{
  "app_id": 123,
  "app_secret": "secret_hex..."
}
```

**新格式**（新站点或迁移后）：
```json
{
  "app_id": 123,
  "app_secret": "secret_hex...",
  "is_active": true
}
```

### Gateway 鉴权逻辑

```python
# 1. 从 Redis 解析 site_key → AppCredential
credential = await resolver.resolve_credential(api_key)

# 2. 检查映射是否存在
if credential is None:
    return 401 "API Key 无效或已失效"

# 3. 新增：检查站点激活状态
if not credential.is_active:
    return 401 "站点已停用或删除"

# 4. 验证签名（如启用）
if signature_required:
    verify_signature(...)

# 5. 通过鉴权，继续处理决策请求
```

### 向后兼容性

- **旧格式数据**：无 `is_active` 字段时默认视为 `True`（激活状态）
- **现有站点**：迁移脚本会根据数据库的 `is_active` 字段同步状态
- **新建站点**：自动写入 `is_active` 字段

## 监控与告警

### 关键指标

1. **停用站点尝试鉴权次数**
   - 日志关键字：`site_inactive_rejected`
   - 含义：已停用站点仍有流量尝试访问
   - 处理：检查对应 CF Worker 是否未清理

2. **Redis 迁移状态**
   - 执行 `migrate_redis_add_is_active.py` 查看输出
   - 关注 `fail_count` 是否为 0

### 日志示例

**停用站点被拒绝**：
```json
{
  "level": "warning",
  "event": "site_inactive_rejected",
  "site_id": 123,
  "path": "/v2/decide",
  "timestamp": "2026-08-09T10:30:00Z"
}
```

**旧站点仍在发送请求**：
如果部署后仍看到已删除站点的日志，说明：
1. CF Worker 未清理 → 执行方案 1 手动清理
2. 迁移脚本未执行 → 执行方案 2 步骤 2
3. Redis 缓存未过期 → 等待 60 秒自动失效

## 常见问题

### Q1：迁移脚本报错 "缺少环境变量"
**A**：确保在 admin-api 容器内执行，或本地配置了以下环境变量：
```bash
export ADMIN_DATABASE_URL="mysql+aiomysql://user:pass@host:3306/db"
export ADMIN_REDIS_URL="redis://:password@host:6379/0"
```

### Q2：迁移后测试站点无法访问
**A**：检查该站点的 `is_active` 状态：
```bash
redis-cli GET "fangyu:app_keys:site_xxx"
# 查看 JSON 中的 is_active 字段
```

如果是 `false`，在后台启用站点：
```bash
curl -X PUT https://defense.foxfingerlab.com/api/v2/sites/123 \
  -H "Authorization: Bearer TOKEN" \
  -d '{"is_active": true}'
```

### Q3：是否需要重启所有 Gateway 实例
**A**：不需要。代码逻辑是向后兼容的，旧实例读取旧格式数据时默认允许通过。部署新版本后逐步替换即可。

### Q4：如何确认 CF Worker 已清理
**A**：两种方式验证：
1. Cloudflare Dashboard 查看 Worker Routes 列表
2. 使用旧站点域名访问，查看是否仍触发防御逻辑：
   ```bash
   curl -I https://old-site.com
   # 如果响应头无 X-Fangyu-* 标记，说明 Worker 已停用
   ```

## 后续优化建议

1. **自动清理机制**
   - 后台删除站点时，提示用户清理对应的 CF Worker / Nginx 适配器
   - 或增加"接入状态检测"，显示哪些站点的代码仍在运行

2. **监控告警**
   - 配置 `site_inactive_rejected` 日志告警
   - 每日统计停用站点的流量尝试次数

3. **强化防护**
   - 考虑在 Redis 映射中增加 `deleted_at` 时间戳
   - Gateway 拒绝超过 N 天的已删除站点请求

## 参考链接

- [站点管理服务代码](../admin-api/src/application/services/site_service.py)
- [Gateway 鉴权中间件](../gateway-api/src/interfaces/http/middleware/app_key.py)
- [Redis 迁移脚本](../scripts/migrate_redis_add_is_active.py)
- [自动化测试](../tests/gateway/test_site_active_validation.py)
