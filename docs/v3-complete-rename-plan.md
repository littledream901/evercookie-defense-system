# V3 完整重命名方案（开发环境）

## 执行说明

由于是开发环境且未部署，可以执行完整的重命名，不需要考虑向后兼容。

## 已完成的工作 ✅

### 1. Gateway 中间件优化
- ✅ `ResolvedAppKey.app_id` → `site_id`
- ✅ 所有引用位置已更新
- ✅ 添加详细注释说明

### 2. Adapters 配置优化
- ✅ Nginx-Lua: `$fangyu_app_id` → `$fangyu_site_id`
- ✅ Cloudflare Worker: `FANGYU_APP_ID` → `FANGYU_SITE_ID`
- ✅ WordPress: 新增 `site_id()`, `site_secret()` 方法

### 3. ClickHouse 查询代码
- ✅ `access_log_query.py`: SQL 中的 `app_id` → `site_id`
- ✅ `analytics_query.py`: SQL 中的 `app_id` → `site_id`
- ✅ `query_spec.py`: 参数重命名

## 待执行的工作 🔄

### 阶段 1：数据库 Schema 重命名

#### PostgreSQL 表结构
需要创建新的迁移脚本修改以下表：

1. **biz_rule 表**
   - `app_id` → `site_id` (外键指向 biz_site.id)

2. **biz_rule_site 表**  
   - 已经使用 `site_id`，无需修改

3. **biz_site 表**
   - `app_id` → `app_id` (保持不变，指向 biz_application.id)

#### ClickHouse 表结构
需要修改表定义：

1. **decision_events 表**
   ```sql
   ALTER TABLE decision_events RENAME COLUMN app_id TO site_id;
   ```

2. **decision_traces 表**
   ```sql
   ALTER TABLE decision_traces RENAME COLUMN app_id TO site_id;
   ```

3. **mv_rule_hits_daily 物化视图**
   ```sql
   -- 需要重建物化视图
   DROP VIEW mv_rule_hits_daily;
   CREATE MATERIALIZED VIEW mv_rule_hits_daily ...
   ```

### 阶段 2：Redis 键格式重命名

#### 规则缓存
- `fangyu:rules:app:{app_id}` → `fangyu:rules:site:{site_id}`

#### API Key 映射
- `fangyu:app_keys:{key}` 中的 `{"app_id": ...}` → `{"site_id": ...}`

### 阶段 3：SDK 参数重命名

#### 前端 SDK 配置
```javascript
// 旧版本
SdSdk.protect({
  apiBase: '...',
  apiKey: 'site_xxx',
  appId: 123  // 实际是站点主键
})

// 新版本
SdSdk.protect({
  apiBase: '...',
  apiKey: 'site_xxx',
  siteId: 123  // 语义清晰
})
```

#### DecisionContext Schema
```python
# 旧版本
class DecisionContext:
    app_id: int  # 实际是站点主键

# 新版本
class DecisionContext:
    site_id: int  # 语义清晰
```

### 阶段 4：前端组件优化

#### 类型定义 (api.d.ts)
```typescript
// 已添加注释，但可以进一步优化接口命名
interface Site {
  id: number              // 站点主键
  site_key: string       // 站点标识
  app_id: number         // 所属应用ID (保持不变)
}
```

#### API 调用
```typescript
// 统一使用 siteId 参数
fetchAccessLogs({ siteId: 123 })
fetchAnalytics({ siteId: 123 })
```

## 迁移脚本

### PostgreSQL 迁移

```python
# alembic/versions/20260808_0003_rename_app_id_to_site_id.py

def upgrade() -> None:
    # 1. 修改 biz_rule 表
    op.alter_column('biz_rule', 'app_id', 
                    new_column_name='site_id',
                    existing_type=sa.BigInteger())
    
    # 2. 重建外键
    op.drop_constraint('fk_rule_app', 'biz_rule', type_='foreignkey')
    op.create_foreign_key('fk_rule_site', 'biz_rule', 'biz_site', 
                         ['site_id'], ['id'], ondelete='SET NULL')
```

### ClickHouse 迁移

```python
# clickhouse_migrations/001_rename_app_id.py

async def upgrade(client: ClickHouseClient):
    # 1. 创建新表结构
    await client.execute("""
        CREATE TABLE decision_events_new (
            event_id String,
            site_id Int32,  -- 重命名
            ...
        ) ENGINE = MergeTree()
        ORDER BY (occurred_at, site_id)
    """)
    
    # 2. 复制数据
    await client.execute("""
        INSERT INTO decision_events_new
        SELECT event_id, app_id as site_id, ...
        FROM decision_events
    """)
    
    # 3. 原子替换
    await client.execute("EXCHANGE TABLES decision_events AND decision_events_new")
    await client.execute("DROP TABLE decision_events_new")
```

### Redis 键迁移

```python
# scripts/migrate_redis_keys.py

async def migrate_redis_keys():
    # 1. 迁移规则缓存键
    pattern = "fangyu:rules:app:*"
    async for key in redis.scan_iter(match=pattern):
        app_id = key.split(":")[-1]
        new_key = f"fangyu:rules:site:{app_id}"
        await redis.rename(key, new_key)
    
    # 2. 迁移 API Key 映射值
    pattern = "fangyu:app_keys:*"
    async for key in redis.scan_iter(match=pattern):
        value = await redis.get(key)
        if value:
            data = json.loads(value)
            if "app_id" in data:
                data["site_id"] = data.pop("app_id")
                await redis.set(key, json.dumps(data))
```

## 验证清单

### 数据库验证
- [ ] PostgreSQL 所有表的 `app_id` 列已重命名为 `site_id`
- [ ] 外键约束正确指向 `biz_site.id`
- [ ] ClickHouse 所有表和视图的列名已更新
- [ ] 历史数据查询正常

### 代码验证
- [ ] 运行 `grep -r "app_id" --include="*.py"` 无遗漏
- [ ] 运行 `grep -r "appId" --include="*.ts" --include="*.vue"` 检查前端
- [ ] 所有测试用例通过
- [ ] API 文档已更新

### 功能验证
- [ ] 访问日志查询正常
- [ ] 分析统计数据正确
- [ ] 规则缓存加载成功
- [ ] SDK 配置生效
- [ ] Adapter 接入正常

## 风险与回滚

### 风险评估
- **低风险**：开发环境，无生产数据
- **数据丢失风险**：几乎为零（可以提前备份）
- **回滚成本**：中等（需要执行反向迁移）

### 回滚方案
```sql
-- PostgreSQL 回滚
ALTER TABLE biz_rule RENAME COLUMN site_id TO app_id;

-- ClickHouse 回滚
EXCHANGE TABLES decision_events AND decision_events_backup;
```

## 执行时间估算

- PostgreSQL 迁移：5-10 分钟
- ClickHouse 迁移：10-20 分钟（取决于数据量）
- Redis 键迁移：5 分钟
- 代码测试验证：30-60 分钟
- **总计：约 1-2 小时**

## 下一步行动

1. ✅ 确认当前已完成的工作
2. 🔄 创建数据库迁移脚本
3. 🔄 执行迁移并验证
4. 🔄 更新所有文档
5. 🔄 提交完整的重命名 commit

---

**更新时间**: 2026-08-08  
**执行人**: TraeCode AI  
**状态**: 部分完成，等待用户确认后继续
