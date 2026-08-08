# V3 架构 app_id/site_id 语义冲突分析报告

**报告时间**：2026-08-08  
**严重程度**：🔴 **高危 - 阻塞 V3 核心功能**  
**影响范围**：全栈（数据库、后端、前端）

---

## 🚨 核心问题概述

### 问题根源
V3 两层架构中引入了 `Application`（应用）和 `Site`（站点）两个概念，但底层数据存储（ClickHouse）和 SDK 配置中仍使用旧的命名约定，导致严重的语义混淆：

```
V3 架构设计（PostgreSQL）:
├── Application (应用)
│   └── id → app_id (应用主键)
└── Site (站点)
    ├── id → site_id (站点主键)
    └── app_id → 外键指向 Application.id

ClickHouse 实际存储:
└── decision_events.app_id → 实际存储的是 Site.id ❌

SDK 配置混淆:
├── apiKey → site_key (字符串标识)
└── appId → Site.id (被误认为 Application.id) ❌
```

---

## 📊 冲突详细分析

### 1. 后端层冲突（严重程度：🔴 高危）

#### 1.1 ClickHouse Schema 语义错误

**文件**：`infrastructure/clickhouse/init.sql`

```sql
CREATE TABLE fangyu.decision_events (
    event_id String,
    app_id UInt64,  -- ❌ 名称误导：实际存储 Site.id
    fingerprint String,
    ...
)
```

**问题**：
- 列名为 `app_id`，但实际存储的是**站点 ID**（`Site.id`）
- 导致无法实现 V3 的"按应用聚合查询"功能
- 所有写入和查询代码都存在语义混淆

**影响范围**：
- ✅ 访问日志查询 - 按站点查询正常工作（巧合）
- ❌ 访问日志查询 - 按应用聚合**无法实现**
- ❌ 分析统计 - 应用级统计**无法实现**
- ❌ 报表导出 - 应用级报表**无法实现**

---

#### 1.2 Gateway 事件写入语义混淆

**文件**：`gateway-api/src/application/services/decision_service.py` (Line 1400)

```python
event = DecisionEvent(
    eventId=uuid.uuid4().hex,
    appId=ctx.app_id,  # ⚠️ ctx.app_id 实际是 Site.id
    fingerprint=ctx.fingerprint,
    ...
)
```

**链路追踪**：
```
1. API Key 中间件解析 site_key
   → app_key.py: AppKeyResolver.resolve_credential()
   → Redis: fangyu:app_keys:{site_key} 
   → 返回: {"app_id": <Site.id>, "app_secret": "..."}
                         ↑
                      实际是站点ID

2. 写入决策上下文
   → DecisionContext.app_id = <Site.id>

3. 事件上报
   → DecisionEvent.appId = ctx.app_id
   → ClickHouse: app_id = <Site.id>
```

**问题**：
- 整个决策链路中 `app_id` 实际承载的是站点 ID
- 变量命名与实际含义完全不符
- 新接入的开发者会被误导

---

#### 1.3 Admin API 查询参数语义混淆

**文件**：`admin-api/src/infrastructure/clickhouse/access_log_query.py` (Line 54)

```python
async def list_paged(
    self,
    *,
    app_id: int | None,  # ⚠️ 参数名叫 app_id，实际接收 site_id
    start: datetime,
    end: datetime,
    ...
) -> tuple[list[dict[str, Any]], int]:
    if app_id is not None:
        clauses.insert(0, "app_id = {app_id}")  # 查询 ClickHouse 的 app_id
        params["app_id"] = app_id
```

**路由层调用**：`admin-api/src/interfaces/http/v2/access_logs.py` (Line 115)

```python
@router.get("")
async def list_access_logs(
    site_id: int | None = Query(default=None, alias="siteId"),  # V2 兼容
    app_id: int | None = Query(default=None, alias="appId"),    # V3 新增
    ...
):
    # 优先使用 site_id，否则使用 app_id
    query_id = site_id if site_id is not None else app_id
    
    rows, total = await service.list_paged(
        app_id=query_id,  # ⚠️ 传入的是 site_id，但参数名是 app_id
        ...
    )
```

**问题**：
1. 前端传入 `appId=5`（期望查询应用 ID=5 的所有站点）
2. 路由层将其传给 `service.list_paged(app_id=5)`
3. ClickHouse 查询 `WHERE app_id = 5`
4. **实际查询到的是 site_id=5 的单个站点数据** ❌

**根本原因**：ClickHouse 的 `app_id` 列存储的是 `site_id`，导致应用级查询失效。

---

#### 1.4 规则缓存强制改写语义

**文件**：`admin-api/src/infrastructure/cache/rule_cache.py` (Line 112)

```python
@staticmethod
def _payload(site_id: int, rule: AnyRule) -> str:
    # 写入 Redis fangyu:rules:{site_id} 时，强制改写 appId
    return rule.model_copy(
        update={"app_id": site_id}  # ⚠️ 把规则的 app_id 改写为 site_id
    ).model_dump_json(by_alias=True)
```

**问题**：
- PostgreSQL 中规则的 `app_id` 可能是应用 ID（V3）或 NULL（全局规则）
- 写入 Redis 分片时，**强制改写为目标站点 ID**
- Gateway 读取时，规则的 `app_id` 字段实际是站点 ID
- 导致规则中的 `app_id` 字段在不同阶段有不同含义

---

### 2. 前端层冲突（严重程度：🟡 中危）

#### 2.1 类型定义混淆

**文件**：`dashboard-ui/src/types/api/api.d.ts` (Line 226-363)

```typescript
// V3 应用类型
interface Application {
  id: number           // 应用主键
  app_key: string      // 应用标识 app_<hex8>
  app_secret?: string  // 应用密钥
}

// V3 站点类型
interface Site {
  id: number           // 站点主键
  site_key: string     // 站点标识 site_<hex8>，同时作为 X-App-Key
  app_id: number       // ⚠️ 外键：所属应用的 Application.id
  site_secret?: string // 站点密钥
}

// V2 兼容类型
interface SiteLegacy extends Site {
  site_id: string      // ⚠️ V2 字段，对应 V3 的 site_key
  app_secret: string   // ⚠️ V2 字段，对应 V3 的 site_secret
}
```

**混淆点**：
1. `Site.app_id` 是外键，指向应用
2. `Site.site_key` 是字符串标识，用于 API 认证
3. `SiteLegacy.site_id` 也是字符串标识，与 `Site.id`（数字主键）完全不同
4. 三个不同概念交织在一起

---

#### 2.2 SDK 配置参数混淆

**文件**：`dashboard-ui/src/views/fangyu/apps/modules/app-integration-drawer.vue` (Line 356-439)

```vue
<script setup lang="ts">
// Line 352：旧 V2 字段
const siteId = computed(() => props.app?.site_id ?? 'YOUR_SITE_ID')
const appSecret = computed(() => props.app?.app_secret ?? 'YOUR_APP_SECRET')

// Line 356-358：数字主键
// SDK 的 appId 要的是数字主键（Site.id），不是 site_id 那个 site_<hex8> 字符串。
// 两者用途不同：site_id 走 X-App-Key header 做身份识别，id 是租户维度。
const numericAppId = computed(() => props.app?.id ?? 0)

// Line 439：SDK 初始化代码
SdSdk.guard({
  apiBase: '${gw.value}',
  apiKey:  '${siteId.value}',        // ⚠️ 传的是 site_key（字符串）
  appId:   ${numericAppId.value}      // ⚠️ 传的是 Site.id（数字主键）
})
</script>
```

**问题**：
- `apiKey` 参数名叫 "key"，但实际是站点标识（`site_key`）
- `appId` 参数名叫 "应用ID"，但实际是站点主键（`Site.id`）
- 开发者容易误认为 `appId` 是 `Application.id`
- 注释中已明确说明混淆，但仍未修正

---

#### 2.3 API 函数命名混乱

**文件**：`dashboard-ui/src/api/apps.ts`

```typescript
// V2 兼容接口（已标注 @deprecated）
fetchGetAppList()              // ⚠️ 实际返回站点列表
fetchRotateAppKey(id: number)  // ⚠️ 实际轮换站点密钥

// V3 应用接口
fetchGetApplicationList()
fetchGetApplicationSites(appId: number)  // ✅ appId 是 Application.id

// V3 站点接口
fetchGetSiteList()
fetchCreateSite(data: { app_id: number, ... })  // ✅ app_id 是外键
```

**混淆点**：
- `fetchGetAppList()` 返回的是站点（Site），不是应用（Application）
- `fetchRotateAppKey(id)` 的参数是站点 ID，但名称暗示是应用
- 新旧接口混用，易导致调用错误

---

#### 2.4 规则接口路径遗留

**文件**：`dashboard-ui/src/api/rules.ts` (Line 44-61)

```typescript
// 规则详情（路径包含 siteId）
export function fetchGetRule(siteId: number, ruleId: number) {
  return request.get<Api.Fangyu.Rule>({
    url: `/api/v2/sites/${siteId}/rules/${ruleId}`  // ⚠️ 规则已全局化
  })
}

// 删除规则（硬编码 siteId=0）
export function fetchDeleteRule(ruleId: number) {
  return request.del<null>({
    url: `/api/v2/sites/0/rules/${ruleId}`  // ⚠️ 硬编码站点ID
  })
}
```

**问题**：
- 规则已迁移为全局+多站点绑定模式
- 但接口路径仍保留 `/sites/${siteId}/rules` 格式
- 导致需要硬编码 `siteId=0` 作为临时方案
- 应改为 `/api/v2/rules/${ruleId}`

---

### 3. 跨层传递冲突（严重程度：🔴 高危）

#### 完整数据流追踪

```
【站点接入】
1. Nginx/SDK 发送请求
   Header: X-App-Key: site_abc12345

【Gateway 鉴权】
2. AppKeyResolver 查询 Redis
   Key: fangyu:app_keys:site_abc12345
   Value: {"app_id": 123, "app_secret": "..."}
          ↑
          实际是 Site.id (站点主键)

3. 写入 DecisionContext
   ctx.app_id = 123  (实际是站点 ID)

4. 规则匹配时读取 Redis
   Key: fangyu:rules:{ctx.app_id}  → fangyu:rules:123
   规则中的 appId 字段 = 123 (被强制改写为站点ID)

5. 写入 ClickHouse
   decision_events.app_id = 123  (实际存储站点ID)

【Admin API 查询】
6. 前端请求访问日志
   GET /api/v2/access-logs?appId=5
   期望：查询应用ID=5下所有站点的日志

7. 路由层处理
   query_id = app_id  (前端传入的5)
   await service.list_paged(app_id=5)

8. ClickHouse 查询
   SELECT * FROM decision_events WHERE app_id = 5
   结果：只查到站点ID=5的数据 ❌
   
   期望结果：查到应用ID=5下所有站点（如 123, 124, 125）的数据
```

---

## 🔧 修复方案

### 方案 A：最小改动（推荐测试环境）

#### 后端修复
1. **重命名 ClickHouse 列**（需要数据迁移）
   ```sql
   -- 添加新列
   ALTER TABLE fangyu.decision_events ADD COLUMN site_id UInt64 DEFAULT 0;
   ALTER TABLE fangyu.decision_traces ADD COLUMN site_id UInt64 DEFAULT 0;
   
   -- 数据迁移
   ALTER TABLE fangyu.decision_events UPDATE site_id = app_id WHERE 1=1;
   ALTER TABLE fangyu.decision_traces UPDATE site_id = app_id WHERE 1=1;
   
   -- 废弃旧列（保留一段时间用于回滚）
   -- ALTER TABLE fangyu.decision_events DROP COLUMN app_id;
   ```

2. **更新事件 Schema**
   ```python
   # shared/src/fangyu_shared/schemas/event.py
   class DecisionEvent(BaseModel):
       site_id: int = Field(..., alias="siteId")  # 重命名
       # app_id: int = Field(..., alias="appId")  # 废弃
   ```

3. **更新查询服务参数**
   ```python
   # admin-api/src/infrastructure/clickhouse/access_log_query.py
   async def list_paged(
       self,
       *,
       site_id: int | None,  # 重命名
       app_id: int | None = None,  # 新增：应用级查询
       ...
   ):
       if site_id is not None:
           clauses.append("site_id = {site_id}")
       elif app_id is not None:
           # 需要先查询应用下的所有站点
           site_ids = await self._get_sites_by_app(app_id)
           clauses.append("site_id IN {site_ids}")
   ```

4. **更新 API 路由**
   ```python
   # admin-api/src/interfaces/http/v2/access_logs.py
   @router.get("")
   async def list_access_logs(
       site_id: int | None = Query(default=None, alias="siteId"),
       app_id: int | None = Query(default=None, alias="appId"),
       ...
   ):
       rows, total = await service.list_paged(
           site_id=site_id,  # 明确传递
           app_id=app_id,    # 明确传递
           ...
       )
   ```

#### 前端修复
1. **SDK 配置参数重命名**
   ```typescript
   // 建议修改 SDK API
   SdSdk.guard({
     apiBase: 'https://gateway.example.com',
     apiKey:  'site_abc12345',  // 或改名为 siteKey
     siteId:  123                // 改名避免与 Application.id 混淆
   })
   ```

2. **规则接口路径迁移**
   ```typescript
   // 从站点级路径迁移到全局路径
   // 旧：/api/v2/sites/{siteId}/rules/{ruleId}
   // 新：/api/v2/rules/{ruleId}
   ```

---

### 方案 B：完整重构（推荐生产环境）

#### 阶段 1：ClickHouse Schema 更新
```sql
-- 创建新表结构
CREATE TABLE fangyu.decision_events_v3 (
    event_id String,
    site_id UInt64,     -- 明确：站点ID
    app_id UInt64,      -- 新增：应用ID（冗余字段，提升查询性能）
    fingerprint String,
    ...
)
ENGINE = ReplacingMergeTree(event_version)
PARTITION BY (toYYYYMM(occurred_at), app_id)  -- 按应用分区
ORDER BY (app_id, site_id, occurred_at, event_id);

-- 数据迁移
INSERT INTO fangyu.decision_events_v3
SELECT 
    event_id,
    app_id as site_id,  -- 旧的 app_id 实际是 site_id
    0 as app_id,         -- 应用ID需要回填（从 site → app 关联查询）
    ...
FROM fangyu.decision_events;
```

#### 阶段 2：Gateway 事件写入更新
```python
# 写入时同时包含 site_id 和 app_id
event = DecisionEvent(
    eventId=uuid.uuid4().hex,
    siteId=ctx.site_id,  # 站点ID
    appId=ctx.app_id,    # 应用ID（从 site.app_id 查询得到）
    fingerprint=ctx.fingerprint,
    ...
)
```

#### 阶段 3：Admin API 支持应用级查询
```python
async def list_paged(
    self,
    *,
    site_id: int | None = None,
    app_id: int | None = None,
    ...
):
    if site_id:
        clauses.append("site_id = {site_id}")
    elif app_id:
        clauses.append("app_id = {app_id}")  # 直接查询应用ID列
```

---

## 📋 修复优先级

### P0（阻塞 V3 核心功能）
1. ✅ **ClickHouse 列重命名**：`app_id` → `site_id`
2. ✅ **事件 Schema 更新**：`DecisionEvent.appId` → `DecisionEvent.siteId`
3. ✅ **查询服务参数重命名**：`AccessLogQueryService.app_id` → `site_id`

### P1（提升代码可维护性）
4. ⚠️ **Gateway 上下文重命名**：`DecisionContext.app_id` → `site_id`
5. ⚠️ **规则缓存语义明确**：注释说明强制改写行为
6. ⚠️ **API 路由统一**：规则接口迁移到全局路径

### P2（优化用户体验）
7. 📝 **SDK 配置参数重命名**：`appId` → `siteId`
8. 📝 **前端变量名统一**：`appOptions` → `siteOptions`
9. 📝 **移除 V2 兼容接口**：逐步迁移到 V3 API

---

## 🎯 影响评估

### 当前状态
- ✅ **V2 单层架构（Site）**：正常工作
- ❌ **V3 两层架构（Application → Site）**：应用级查询**无法实现**
- ⚠️ **SDK 接入**：工作正常，但参数命名误导

### 修复后状态
- ✅ 支持按站点查询（兼容 V2）
- ✅ 支持按应用聚合查询（V3 核心功能）
- ✅ 代码语义清晰，易于维护
- ✅ 新接入开发者不会被误导

---

## 📚 相关文档

- [V3 迁移完成报告](./v3-migration-completed.md)
- [V3 迁移完整总结](./v3-migration-complete-summary.md)
- [迁移方案文档](./migration-app-site-separation.md)

---

**最后更新**：2026-08-08  
**报告版本**：v1.0  
**优先级**：🔴 高危 - 建议立即修复
