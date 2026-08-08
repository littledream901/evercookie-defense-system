# app_id 设计说明

## 概述

`app_id` 是 Evercookie Defense System 中**站点（Application）的内部数字主键**，用于在系统各层之间唯一标识一个受保护的站点。

---

## 核心概念

### 1. 站点模型（Application）

系统使用 **Application** 实体来管理受保护的站点，每个 Application 包含：

```python
class ApplicationModel:
    id: int                    # 内部数字主键（即 app_id）
    site_id: str              # 外部唯一标识（格式: site_<hex8>）
    name: str                 # 站点名称
    domain: str               # 主域名
    app_secret: str           # HMAC 签名密钥
    access_mode: str          # 接入模式（sdk/adapter）
    gateway_url: str          # 专属网关地址（可选）
    owner_user_id: int        # 站点所有者
    ...
```

### 2. 两个 ID 的关系

| 字段 | 类型 | 可见性 | 用途 |
|------|------|--------|------|
| **`id` (app_id)** | `int` (UInt64) | 内部 | 数据库主键、关联外键、ClickHouse 分区键 |
| **`site_id`** | `string` | 外部 | API Key、客户端标识、人类可读标识 |

**关系**：
- `id` (app_id) 是**内部数字主键**，用于数据库关联和高性能查询
- `site_id` 是**外部字符串标识**，格式为 `site_<hex8>`（如 `site_a1b2c3d4`）
- 一个 Application 同时拥有这两个 ID，它们是一对一的映射关系

---

## 使用场景

### 1. **ClickHouse 事件表**

在决策事件表中，`app_id` 用作**站点维度的分区键**：

```sql
CREATE TABLE fangyu.decision_events (
    event_id        String,
    app_id          UInt64,    -- 站点主键，用于分区查询
    fingerprint     String,
    ip              String,
    ...
)
ENGINE = ReplacingMergeTree(event_version)
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (app_id, occurred_at, event_id)  -- app_id 在排序键首位
```

**优势**：
- ✅ 数字类型，占用空间小（8字节 vs 字符串 12-16 字节）
- ✅ 排序和比较性能高
- ✅ 自然分区键，适合多租户查询隔离

### 2. **访问日志查询**

后端 API 使用 `app_id` 过滤访问日志：

```python
# admin-api/src/infrastructure/clickhouse/access_log_query.py
async def list_paged(self, *, app_id: int | None, ...):
    where_sql = "app_id = {app_id} AND occurred_at >= {start}"
    rows = await self._client.fetch(f"""
        SELECT * FROM decision_events
        WHERE {where_sql}
        ORDER BY occurred_at DESC
    """, {"app_id": app_id, "start": start})
```

**前端传参**：
```typescript
// 前端使用 siteId（数字类型）查询
fetchGetAccessLogList({ siteId: 123, page: 1, pageSize: 50 })
```

### 3. **规则关联**

规则通过 `site_id` 外键关联到站点：

```python
# admin-api/src/infrastructure/repositories/models.py
class RuleModel:
    site_id: int  # 外键关联 biz_application.id

class RuleSiteModel:
    rule_id: int
    site_id: int  # 外键关联 biz_application.id
```

**历史演变**：
- 原先字段名为 `app_id`，在 2026-08-02 重命名为 `site_id`
- 含义更清晰：关联的是 `biz_application.id`（站点主键）
- 迁移文件：`20260802_0012_rename_rule_app_id_to_site_id.py`

### 4. **决策请求流程**

```
客户端 → Gateway API → Decision Service → Redis/ClickHouse
  |           |              |                  |
site_id  → app_id 查找 → 规则匹配 → 事件写入（app_id）
```

1. **客户端**使用 `site_id`（如 `site_a1b2c3d4`）标识自己
2. **Gateway** 查找对应的 `app_id`（数字主键）
3. **Decision Service** 使用 `app_id` 匹配规则
4. **ClickHouse** 写入事件时携带 `app_id` 用于分区和查询

---

## 设计原理

### 为什么需要两个 ID？

#### `app_id`（数字主键）的优势
1. **高性能查询**
   - 数字比较比字符串快 3-5 倍
   - ClickHouse 按数字分区效率更高
   - 索引占用空间更小

2. **自然递增**
   - 数据库自增主键，天然保证唯一性
   - 适合作为外键关联

3. **多租户隔离**
   - ClickHouse 查询时按 `app_id` 分区，避免跨站点数据泄漏
   - WHERE 条件中 `app_id = ?` 比字符串匹配快

#### `site_id`（字符串标识）的优势
1. **API Key 功能**
   - 客户端使用 `site_id` 作为 `X-App-Key` 请求头
   - 无需维护独立的 API Key 表
   - 格式 `site_<hex8>` 人类可读且不易冲突

2. **安全性**
   - 不暴露数字主键，避免遍历攻击
   - 随机十六进制，难以猜测

3. **可读性**
   - 日志、配置文件中便于识别
   - 方便客户集成和调试

---

## 命名演变

### 历史变更

| 时间 | 变更 | 说明 |
|------|------|------|
| 初始版本 | `biz_rule.app_id` | 规则表使用 `app_id` 关联站点 |
| 2026-08-02 | 重命名为 `site_id` | 含义更清晰，避免与主键 `id` 混淆 |
| 当前 | 数据库: `site_id`<br>ClickHouse: `app_id` | 分层使用不同术语 |

### 当前命名规范

| 层级 | 字段名 | 类型 | 含义 |
|------|-------|------|------|
| **MySQL 数据库** |
| `biz_application.id` | `int` | 站点主键（内部 ID） |
| `biz_application.site_id` | `string` | 站点唯一标识（外部 Key） |
| `biz_rule.site_id` | `int` | 外键，关联 `biz_application.id` |
| **ClickHouse** |
| `decision_events.app_id` | `UInt64` | 站点主键（与 MySQL 的 `id` 对应） |
| **前端 API** |
| `siteId` | `number` | 站点主键（驼峰命名） |
| **后端 Schema** |
| `app_id` | `int` | DecisionEvent 中的站点主键 |

---

## 查询示例

### 1. 查询某站点的访问日志

```typescript
// 前端
const logs = await fetchGetAccessLogList({
  siteId: 123,  // 使用数字主键
  page: 1,
  pageSize: 50
})
```

```python
# 后端
async def list_access_logs(site_id: int | None):
    rows = await query_service.list_paged(
        app_id=site_id,  # 传递给 ClickHouse 查询
        start=start,
        end=end
    )
```

```sql
-- ClickHouse
SELECT * FROM fangyu.decision_events
WHERE app_id = 123  -- 数字主键，高性能过滤
  AND occurred_at >= '2026-08-01'
ORDER BY occurred_at DESC
LIMIT 50
```

### 2. 查询某站点的规则列表

```python
# 后端
rules = await rule_repo.list_by_site(site_id=123)
```

```sql
-- MySQL
SELECT r.* FROM biz_rule r
WHERE r.site_id = 123  -- 关联站点主键
  AND r.status = 'published'
ORDER BY r.priority DESC
```

---

## 最佳实践

### ✅ 推荐做法

1. **ClickHouse 查询始终使用 `app_id`**
   ```python
   WHERE app_id = {app_id}  # 数字主键，性能最优
   ```

2. **API 参数使用 `siteId`（驼峰）**
   ```typescript
   fetchGetAccessLogList({ siteId: 123 })
   ```

3. **客户端认证使用 `site_id`（字符串）**
   ```http
   X-App-Key: site_a1b2c3d4
   ```

4. **数据库外键使用 `site_id`（关联主键）**
   ```python
   site_id: Mapped[int] = mapped_column(ForeignKey("biz_application.id"))
   ```

### ❌ 避免的做法

1. ❌ 在 ClickHouse 中使用字符串 `site_id` 作为分区键
2. ❌ 在 API 响应中暴露数字 `app_id`（应使用 `site_id` 字符串）
3. ❌ 混用 `app_id` 和 `site_id` 的命名（同一层级保持一致）

---

## 总结

| 特性 | `id` (app_id) | `site_id` |
|------|---------------|-----------|
| **类型** | 数字 (int/UInt64) | 字符串 (site_<hex8>) |
| **用途** | 内部主键、ClickHouse 分区键 | API Key、客户端标识 |
| **可见性** | 内部（数据库、ClickHouse） | 外部（API、客户端） |
| **性能** | 高（数字比较快） | 中（字符串比较慢） |
| **安全性** | 低（顺序递增，可预测） | 高（随机十六进制） |
| **可读性** | 低（纯数字） | 高（site_ 前缀） |

**设计哲学**：
- **内部用数字**（app_id）：追求性能和效率
- **外部用字符串**（site_id）：追求安全和可读性
- **前端类型定义不需要 app_id**：因为前端始终通过 `siteId` 查询，后端自动映射到 ClickHouse 的 `app_id`

---

## 相关文档

- [Application 领域实体](../admin-api/src/domain/app/entities.py)
- [ClickHouse 表结构](../infrastructure/clickhouse/init.sql)
- [访问日志查询服务](../admin-api/src/infrastructure/clickhouse/access_log_query.py)
- [字段重命名迁移](../admin-api/alembic/versions/20260802_0012_rename_rule_app_id_to_site_id.py)
