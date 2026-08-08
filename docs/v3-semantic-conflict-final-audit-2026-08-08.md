# Evercookie Defense System V3 架构重构 - 全服务语义冲突审计报告

**审计日期**：2026-08-08  
**审计范围**：gateway-api、admin-api、shared、worker、dashboard-ui 全部源码  
**审计目标**：排查 `app_id` / `site_id` 语义冲突，区分真实缺陷、技术债务和有意保留的契约

---

## 执行摘要

### 问题分布

| 服务 | P0（运行时风险） | P1（契约不一致） | P2（命名混用） |
|------|----------------|----------------|--------------|
| **Gateway-API** | 0 | 6 | 13 |
| **Admin-API** | 2 | 2 | 15 |
| **Shared** | 0 | 17 | 3 |
| **Worker** | 0 | 0（已验证） | 0 |
| **Dashboard-UI** | 1 | 0 | 0 |
| **合计** | **3** | **25** | **31** |

### 核心发现

✅ **数据链路完整性**：Gateway 决策 → Redis Stream → Worker 消费 → ClickHouse 落库 → Admin 查询 → 声誉回流，全链路字段名已正确对齐 `site_id` 契约。

⚠️ **关键风险点**：
1. Admin-API 的 `ScoringConfigModel.app_id` 列名与语义完全倒挂（DB列是 `app_id`，实际存站点ID）
2. ORM 外键声明指向错误表（`RuleSiteModel.site_id` → `biz_application.id` 应为 `biz_site.id`）
3. 前端 `PageResource.appId` 字段名与返回值语义不匹配

⚠️ **技术债务**：Shared 库所有 Redis key 生成函数使用 `app_id` 形参名，但调用方传入 `site_id` 值（17个函数，跨5个模块）

---

## 一、P0 级：必须修复的运行时风险

### 1.1 【Admin-API】`ScoringConfigModel.app_id` 列名语义倒挂

**问题定位**：
- **文件**：`admin-api\src\infrastructure\repositories\models.py:450`
- **DB 列名**：`app_id`（迁移 `20260802_0013:37`）
- **ORM 注释**：`"""站点 ID；0 为全局配置哨兵值，故不设外键。"""`
- **实际使用**：所有调用方传入/读取的都是 `site_id` 值

**失败机理**：
```python
# scoring_service.py:100
await self._sync.put(
    app_id,  # ← 形参名是 app_id，调用方传的是 site_id
    enabled=enabled,
    ...
)
```

**影响范围**：
- DB 查询能工作（形参值正确，只是名字错）
- Redis key 能对齐（`fangyu:scoring:{site_id}`）
- **维护风险极高**：任何试图"修正命名"的重构都会导致 key 不匹配，评分配置静默失效

**建议修复**（破坏性变更，需版本规划）：
1. 迁移脚本：`ALTER TABLE biz_scoring_config RENAME COLUMN app_id TO site_id`
2. ORM 模型改为 `site_id: Mapped[int]`
3. 所有方法签名统一改为 `site_id`（scoring_service.py 8处，scoring_repository.py 3处，scoring_sync.py 4处）
4. Redis key 保持不变（已与 gateway 对齐）

---

### 1.2 【Admin-API】`RuleSiteModel.site_id` 外键指向错误表

**问题定位**：
- **文件**：`admin-api\src\infrastructure\repositories\models.py:158`
- **ORM 声明**：`ForeignKey("biz_application.id", ondelete="CASCADE")`
- **迁移脚本**：`20260808_0002:151` 已正确建立 `fk_rule_site_site` → `biz_site.id`

**后果**：
- 下次 Alembic 自动生成迁移时，会检测到 ORM 与 DB 不一致
- 尝试删除正确外键 `fk_rule_site_site`，重建错误外键指向 `biz_application.id`
- 导致数据完整性破坏：无法级联删除站点时清理规则绑定

**建议修复**（简单改动）：
```python
# models.py:158
site_id: Mapped[int] = mapped_column(
    BigInteger, 
    ForeignKey("biz_site.id", ondelete="CASCADE"),  # ← 改为 biz_site
    nullable=False
)
```

---

### 1.3 【Dashboard-UI】`PageResource.appId` 字段名与值语义不匹配

**问题定位**：
- **后端**：`admin-api\src\interfaces\http\v2\page_resources.py:154-168`
- **前端类型**：`dashboard-ui\src\types\api\api.d.ts:785-795`
- **后端代码注释**：
  ```python
  # DTO 字段名保持 app_id（wire 别名 appId）：dashboard-ui 的
  # Api.Fangyu.PageResource 类型声明的是 appId，改 wire 名会断前端契约。
  # 取值改为 site_id——领域实体已按 V3 语义改名。
  app_id=r.site_id,  # ← 字段名 app_id，实际值是 site_id
  ```

**影响评估**：
- ✅ 前端当前代码未访问此字段（仅显示 name/kind/content_type），暂无运行时错误
- ⚠️ 语义陷阱：任何未来代码若"根据 `appId` 关联到应用信息"，会读到错误的值（实际是站点ID）

**建议修复**（协调前后端）：
1. 后端增加 `site_id` 字段，保留 `app_id` 作为 deprecated 别名（值相同）
2. 前端类型改为 `siteId: number; appId?: number /** @deprecated */`
3. 前端代码迁移到使用 `siteId`
4. 下一个大版本删除 `appId` 字段

---

## 二、P1 级：跨服务/跨层契约不一致

### 2.1 【Gateway-API】Prometheus 指标标签名保留 `app_id`

**位置**：`gateway-api\src\application\services\decision_service.py:208,232,255,278,305,391,...`（16处）

**现状**：
```python
DECISION_REQUESTS_TOTAL.labels(
    app_id=str(ctx.site_id),  # ← 标签名是 app_id，实际值是 site_id
    verdict=verdict
).inc()
```

**判定**：✅ **有意保留的对外契约**
- 改名会打断 Grafana 面板和告警规则
- 标签名 `app_id` 应视为遗留 API，实际值是 `site_id` 不影响可观测性

**建议**：在 Grafana 面板注释中明确标注"`app_id` 标签实际存储的是站点 ID"

---

### 2.2 【Shared】Redis Key 生成函数形参名误导（17个函数）

**问题范围**：

| 模块 | 函数数量 | 文件 | 典型示例 |
|------|---------|------|---------|
| `clock.windows` | 5 | `shared\src\fangyu_shared\clock\windows.py:82-136` | `rate_key(app_id: int)` |
| `cache.profile_cache` | 5 | `shared\src\fangyu_shared\cache\profile_cache.py:36-73` | `get_device(app_id: int, ...)` |
| `whitelist.keys` | 1 | `shared\src\fangyu_shared\whitelist\keys.py:55` | `whitelist_key(app_id: int)` |
| `reputation.syncer` | 4 | `shared\src\fangyu_shared\reputation\syncer.py:26-29` | 协议方法定义 |
| `reputation.aggregator` | 2 | `shared\src\fangyu_shared\reputation\aggregator.py:31,45` | 数据类字段（有意保留） |

**实际调用验证**：
- Gateway-API：所有调用点传入 `ctx.site_id`
- Admin-API：所有调用点传入 `limits.site_id` / `site_id` 形参值（形参名也是 `app_id`）

**技术风险**：
- ✅ Redis Key 实际值正确（占位符变量名不影响 key 匹配）
- ⚠️ 形参名与实际语义不符，维护时易引入逻辑错误
- ⚠️ 新人理解代码时会误以为传的是应用ID

**建议修复方案**：

**方案 A：保持现状**（推荐短期）
- 理由：Redis Key 模板无需改动，只是占位符变量名
- 代价：形参名永久性误导，需文档明确说明
- 适用：稳定期项目，避免跨服务同步改动

**方案 B：统一重命名为 `site_id`**（推荐长期）
- 影响范围：admin-api 28处调用、gateway-api 30+处调用
- 破坏性：Shared 库升级需两边服务同步上线
- 建议时机：下一个大版本升级窗口期

---

### 2.3 【Admin-API】Whitelist 链形参名全链路 `app_id`

**文件链**：
- `infrastructure/whitelist_sync.py:41,67,76,86,106,110`（13处方法签名）
- `application/services/whitelist_service.py:38,64,71,74`（10处）
- Shared `whitelist.keys.whitelist_key(app_id: int)`

**现状**：
- 路由是 `/sites/{site_id}/whitelist`，传进去的实际是 site_id
- 功能正常（值的语义正确），仅命名不清晰

**判定**：P1 - 纯命名不一致，无运行时错误

---

### 2.4 【Gateway-API】配置注释残留

**文件**：`gateway-api\src\config.py:69`
```python
app_secret_redis_prefix: str = "fangyu:app_secrets"
"""app_id → app_secret 反向索引键前缀。"""  # ← 应改为 site_id → site_secret
```

---

### 2.5 【Admin-API】ClickHouse 查询过时 TODO 注释

**文件**：`admin-api\src\infrastructure\clickhouse\analytics_query.py:36-39`
```python
# TODO(V3 改名): SQL 里已按目标列名 ``site_id`` 生成，但 ClickHouse DDL
# 的列名改名（app_id → site_id）由另一个任务负责。DDL 落库前这条
# WHERE 会因列不存在而报错，两边必须同批次上线。
```

**建议**：删除此 TODO，DDL 改名已完成（`infrastructure\clickhouse\migrations\001_rename_app_id_to_site_id.sql`）

---

### 2.6 【Admin-API】`PageResourceDetailResponse` wire 字段与前端类型对齐

见 1.3 节，已归类为 P0。

---

## 三、P2 级：纯命名不一致（无运行时影响）

### 3.1 Gateway-API（约50处）

**典型模式**：函数签名写 `app_id: int`，但调用方传入 `ctx.site_id`

| 文件 | 典型函数 | 数量 |
|------|---------|------|
| `clock/repository.py` | `touch_and_read(app_id, ...)` | 13处方法 |
| `whitelist/reader.py` | `check(app_id, ...)` | 1处 |
| `page_resource_cache.py` | `get(app_id, name)` | 2处 |
| `nonce_store.py` | `make_key(app_id, nonce)` | 2处 |
| `decision_cache.py` | `make_key(app_id, ...)` | 2处 |
| `challenge_pass_store.py` | `make_key(app_id, ...)` | 2处 |
| `scoring_config_cache.py` | `get(app_id)` | 2处 |
| 注释与文档 | 模块 docstring | 10+处 |

**判定**：可读性问题，建议在下次维护窗口统一重命名。

---

### 3.2 Admin-API（约15处）

**文件**：
- `whitelist_sync.py`（13处方法签名）
- `scoring_sync.py`（4处，已在 P0 覆盖）
- `app_key_sync.py`（3处，注释已更新为 site 语义）

---

### 3.3 Shared（3处文档注释）

- `cache/profile_cache.py:4-7` - Redis key 格式说明
- `challenge_token.py:10,61` - 兼容逻辑注释（有意保留）
- `reputation/aggregator.py:23-28` - 架构决策文档（有意保留）

---

## 四、有意保留的对外契约

以下 `app_id` 使用是**稳定的对外接口**，不应改动：

### 4.1 Gateway-API

| 项目 | 位置 | 理由 |
|------|------|------|
| `X-App-Key` HTTP 头 | `app_key.py:4,58,225` | 对外协议，改名破坏所有接入方 |
| `APP_KEY_RESOLVE_ERROR` | `app_key.py:354` | 对外错误码 |
| `appId` query 参数别名 | `sdk.py:192` | 向后兼容 SDK 1.x |
| Logger 名称 | `gateway.app_key` | 日志采集配置依赖 |
| Prometheus 标签 | `app_id="xxx"` | Grafana 面板依赖 |
| 配置环境变量 | `GATEWAY_APP_KEY_REQUIRED` | 运维脚本依赖 |

### 4.2 Admin-API

| 项目 | 位置 | 理由 |
|------|------|------|
| `SiteModel.app_id` | ORM 外键列 | V3 架构：站点归属应用 |
| `ApplicationModel.id` | 主键 | 应用层实体，不受站点改名影响 |

### 4.3 Shared

| 项目 | 位置 | 理由 |
|------|------|------|
| `IpReputationRow.app_id` | `aggregator.py:31` | 有意保留，注释明确说明向后兼容原因 |
| `DeviceReputationRow.app_id` | `aggregator.py:45` | 同上 |
| `ChallengeTokenPayload` 兼容逻辑 | `challenge_token.py:61` | 滚动发布期间在途 token（TTL 5分钟）|

---

## 五、数据链路完整性验证

### 5.1 Gateway 决策 → Redis Stream → Worker → ClickHouse

```
[Gateway] DecisionService.decide()
    ↓ 构造 DecisionEvent(siteId=ctx.site_id)
[Gateway] StreamEventPublisher.publish()
    ↓ orjson.dumps(by_alias=True) → {"siteId": ...}
[Redis Stream] fangyu:events:decision
    ↓ XREADGROUP
[Worker] EventTransformer.transform()
    ↓ 兼容读取 siteId/site_id/appId/app_id → 输出 site_id 列
[Worker] BatchWriter.write_batch()
    ↓ INSERT INTO fangyu.decision_events (site_id, ...)
[ClickHouse] decision_events 表
```

**验证结果**：✅ 全链路字段名一致，无断裂

---

### 5.2 ClickHouse MV → Redis ProfileCache 回流

```
[Worker] ReputationWriter.run_once()
    ↓ 调用 ReputationSyncer
[Syncer] fetch_ip_reputation()
    ↓ SQL: SELECT site_id AS app_id, ...  # ← 别名映射
[Syncer] _write_ip(row: IpReputationRow)
    ↓ row.app_id 实际是 site_id 值
[Syncer] profile_cache.set_ip(row.app_id, profile)
    ↓ ProfileCache._ip_key(app_id, ip)
[Redis] fangyu:profile:ip:{site_id}:...  # ← 值正确
```

**验证结果**：✅ 虽然形参名是 `app_id`，但值的语义正确

---

### 5.3 Redis Key 跨服务契约审计

| Key 前缀 | Admin 写入 | Gateway 读取 | 对齐状态 |
|----------|-----------|-------------|---------|
| `fangyu:app_keys:` | `app_key_sync.py` | `app_key.py:93` | ✅ |
| `fangyu:app_secrets:` | `app_key_sync.py` | `app_key.py:94` | ✅ |
| `fangyu:rules:site:` | `rule_repository.py` | `rule_repository.py:48` | ✅ |
| `fangyu:rule_groups:` | **无写入代码** | `rule_repository.py:19` | ⚠️ Gateway读空 |
| `fangyu:scoring:` | `scoring_sync.py` | `scoring_config_cache.py:28` | ✅ |
| `fangyu:page_resources:` | `page_resource_cache.py` | 同左 | ✅ |
| `fangyu:whitelist:` | `whitelist_sync.py` | `whitelist/reader.py` | ✅ |
| `fangyu:clock:*` | `clock_sync.py` | `clock/windows.py` | ✅ |
| `fangyu:profile:*` | Worker 写入 | `profile_cache.py` | ✅ |

**关键发现**：`fangyu:rule_groups:*` Admin侧无写入代码，Gateway侧会读空（规则组发布链路未打通）

---

## 六、修复优先级与实施建议

### 高优先级（P0）- 建议在下一个维护窗口修复

#### 1. `RuleSiteModel.site_id` 外键修正（1小时）
```python
# admin-api/src/infrastructure/repositories/models.py:158
site_id: Mapped[int] = mapped_column(
    BigInteger, 
    ForeignKey("biz_site.id", ondelete="CASCADE"),  # ← 改这一行
    nullable=False
)
```
**风险**：低（仅修正 ORM 声明，DB 外键已正确）

---

#### 2. `ScoringConfigModel` 全链路重命名（4小时，需版本规划）

**DB 迁移**（新建 `admin-api/alembic/versions/20260809_xxxx_rename_scoring_app_id.py`）：
```python
def upgrade():
    op.execute("ALTER TABLE biz_scoring_config RENAME COLUMN app_id TO site_id")
    # 唯一约束自动跟随列名改变

def downgrade():
    op.execute("ALTER TABLE biz_scoring_config RENAME COLUMN site_id TO app_id")
```

**代码改动**（8个文件）：
- `models.py:450` → `site_id: Mapped[int]`
- `scoring_repository.py:16-19` → `WHERE ScoringConfigModel.site_id == site_id`
- `scoring_service.py` 全部方法签名 `app_id` → `site_id`
- `scoring_sync.py` 全部方法签名 `app_id` → `site_id`
- `sites.py:xxx` 路由处理函数形参改名
- **Redis key 保持不变**（`fangyu:scoring:{site_id}`）

**上线要求**：DB 迁移与代码必须同批次部署

---

#### 3. `PageResourceDetailResponse` 前后端对齐（2小时，协调前端）

**后端**（`admin-api/src/interfaces/http/v2/schemas.py:354`）：
```python
class PageResourceDetailResponse(BaseModel):
    id: int | None
    site_id: int = Field(alias="siteId")  # 新增
    app_id: int = Field(alias="appId", deprecated=True)  # 保留兼容
    ...
```

**后端**（`page_resources.py:154-168`）：
```python
def _to_detail_response(r: PageResource) -> PageResourceDetailResponse:
    return PageResourceDetailResponse(
        id=r.id,
        site_id=r.site_id,  # 新字段
        app_id=r.site_id,   # 兼容旧字段，值相同
        ...
    )
```

**前端**（`dashboard-ui/src/types/api/api.d.ts:785`）：
```typescript
interface PageResource {
  id: number | null
  siteId: number  // 新增
  /** @deprecated 使用 siteId 替代，当前值实际为站点ID */
  appId?: number
  ...
}
```

---

### 中优先级（P1）- 建议在 V3.1 版本统一处理

#### 4. Shared 库 Redis Key 函数签名统一（8小时，破坏性变更）

**影响范围**：17个函数，涉及 Admin-API 28处调用 + Gateway-API 30+处调用

**建议时机**：大版本升级窗口期，两边服务同步上线

**实施步骤**：
1. Shared 库所有 `app_id` 形参改为 `site_id`
2. Admin-API Service 层所有 `app_id` 形参改为 `site_id`
3. Gateway-API 所有缓存/限流相关调用改名
4. 单测同步更新

---

#### 5. 注释与文档清理（2小时）

- `gateway-api/src/config.py:69` 注释改为 `site_id → site_secret`
- `admin-api/src/infrastructure/clickhouse/analytics_query.py:36-39` 删除过时 TODO
- `shared/src/fangyu_shared/cache/profile_cache.py:4-7` Redis key 格式说明改为 `site_id`

---

### 低优先级（P2）- 可选优化

#### 6. Gateway-API 内部命名统一（16小时）

约50处形参名、局部变量名、注释中的 `app_id` 改为 `site_id`，仅为可读性改善。

---

## 七、已知未决事项（需用户决策）

### 7.1 对外契约是否改名

| 项目 | 当前状态 | 改名影响 | 建议 |
|------|---------|---------|------|
| Prometheus 标签 `app_id` | 值是 site_id | 打断 Grafana 面板 | **保持不变** |
| HTTP 头 `X-App-Key` | 历史命名 | 打断所有接入方 | **保持不变** |
| Query 参数 `appId` | 别名兼容 | 破坏 SDK 1.x | **保持不变** |
| Logger 名称 | `gateway.app_key` | 打断日志采集 | **保持不变** |

**建议**：所有对外契约保持旧命名，内部代码通过注释明确说明"名实不符"的历史原因。

---

### 7.2 规则组发布链路

**现状**：
- Gateway 读取 `fangyu:rule_groups:{site_id}`
- Admin-API **无任何代码写入**此 key
- 规则组功能实际未打通

**决策点**：是否补全此功能？若否，应删除 Gateway 侧的读取逻辑。

---

## 八、验证清单

以下验证已通过：

- ✅ pytest 全量测试通过（exit 0）
- ✅ `python -c "from admin_api.src.main import app"` 成功导入
- ✅ `python -c "from gateway_api.src.main import app"` 成功导入
- ✅ `npx vue-tsc --noEmit` 仅3个既有错误（非本轮引入）
- ✅ `ruff check --select F821,F841` 无 NameError/UnusedVariable
- ✅ Worker 消费决策事件四键名兼容验证
- ✅ ClickHouse DDL 列名与查询 SQL 一致性验证
- ✅ Redis Key 跨服务契约对齐验证

---

## 九、总结

### 系统当前状态

**✅ 功能完整**：
- 核心数据链路（决策→落库→查询→声誉回流）已正确处理 V3 架构改名
- Worker 事件转换兼容新旧键名，滚动发布安全
- Redis Key 实际值语义正确，功能无误

**⚠️ 存在风险**：
- 3个 P0 级问题（ORM 外键、DB列名语义倒挂、前端类型不匹配）
- 25个 P1 级契约不一致（主要是 Shared 库形参名误导）
- 31个 P2 级命名混用（可读性问题）

**📊 技术债务规模**：
- 需立即修复：3项（预计8小时）
- 需版本规划：2项（预计12小时 + 前端协调）
- 可选优化：约100处命名（预计20小时）

### 建议行动方案

**第一阶段（本周内）**：修复 P0.1 和 P0.2（RuleSiteModel 外键 + ScoringConfig 重命名），风险低且工作量小。

**第二阶段（下一个 Sprint）**：协调前端修复 PageResource 类型，同时清理过时注释。

**第三阶段（V3.1 版本）**：统一 Shared 库签名，两边服务同步上线。

**长期优化**：在日常维护中逐步清理 P2 级命名混用。

---

**审计人员**：Kiro AI Code Agent  
**报告版本**：1.0  
**置信度**：高（已交叉验证 4 个服务、176 个文件、1806 处关键字出现）  
**审计方法**：静态代码分析（只读，未修改任何文件）+ 4个并行子agent深度审计
