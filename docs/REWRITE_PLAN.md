# Evercookie Defense System V2 - 完整重写计划

**文档版本**: V2.0 Rewrite Plan
**编制日期**: 2026-07-31
**目标目录**: `e:\Python\evercookie-defense-system\Evercookie Defense System V2`
**策略**: 全新重写，不修改现有代码，仅参考现有业务逻辑

---

## 一、重写策略与原则

### 1.1 核心原则

1. **零耦合原则**：新代码完全独立，不导入旧代码任何模块
2. **业务对齐原则**：保持与 V1 相同的业务逻辑与 API 契约（保证平滑迁移）
3. **架构升级原则**：采用 DDD（领域驱动设计）+ 分层架构，替代原有的扁平结构
4. **共享优先原则**：通用逻辑先入 `shared/` 包，各服务通过依赖引用
5. **测试先行原则**：核心模块 TDD 开发，覆盖率不低于 80%

### 1.2 迁移策略

```
┌────────────────────────────────────────────────────┐
│  第一阶段：基础设施（shared/ + infrastructure/）      │
│  第二阶段：领域模型（domain/）                        │
│  第三阶段：应用服务（application/）                    │
│  第四阶段：接口适配（interfaces/）                     │
│  第五阶段：前端 + SDK + Adapters                     │
│  第六阶段：数据迁移 + 灰度切换                          │
└────────────────────────────────────────────────────┘
```

---

## 二、新目录结构总览

```
Evercookie Defense System V2/
│
├── shared/                            # 【新增】跨服务共享包
│   ├── event_normalizer/              # 事件标准化（消除 admin/worker 冗余）
│   ├── redis_manager/                 # Redis 统一连接池
│   ├── clickhouse_manager/            # ClickHouse 统一客户端
│   ├── exceptions/                    # 统一异常体系
│   ├── logging/                       # 结构化日志
│   ├── metrics/                       # Prometheus 指标封装
│   ├── schemas/                       # 跨服务 Pydantic 模型
│   └── utils/                         # 通用工具（时间/加密/校验）
│
├── gateway-api/                       # 决策引擎服务
│   ├── src/
│   │   ├── domain/                    # 领域层
│   │   │   ├── decision/              # 决策领域
│   │   │   │   ├── entities.py        # 决策实体
│   │   │   │   ├── value_objects.py   # 值对象
│   │   │   │   └── policies.py        # 决策策略
│   │   │   ├── profile/               # 特征画像领域
│   │   │   ├── rule/                  # 规则领域
│   │   │   └── risk/                  # 风险领域
│   │   ├── application/               # 应用层（用例编排）
│   │   │   ├── services/
│   │   │   │   ├── decision_service.py       # 决策主流程
│   │   │   │   ├── profile_builder.py        # 画像构建
│   │   │   │   ├── precision_matcher.py      # 精准规则
│   │   │   │   ├── security_checker.py       # 安全检查
│   │   │   │   └── disposition_resolver.py   # 处置解析
│   │   │   └── dto/                   # 数据传输对象
│   │   ├── infrastructure/            # 基础设施层
│   │   │   ├── cache/                 # 决策缓存实现
│   │   │   ├── rule_repo/             # 规则仓储实现
│   │   │   ├── event_publisher/       # 事件发布
│   │   │   └── mmdb/                  # GeoIP 数据源
│   │   └── interfaces/                # 接口层
│   │       └── http/
│   │           ├── v2/                # V2 新接口
│   │           │   ├── decide.py      # 完整决策
│   │           │   ├── decide_fast.py # 快速决策
│   │           │   └── rule_test.py   # 规则沙箱
│   │           └── middleware/        # 中间件
│   ├── tests/
│   ├── config/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── admin-api/                         # 管理后台 API
│   ├── src/
│   │   ├── domain/
│   │   │   ├── user/                  # 用户领域
│   │   │   ├── app/                   # 应用配置领域
│   │   │   ├── rule/                  # 规则配置领域
│   │   │   ├── rbac/                  # 权限领域
│   │   │   └── analytics/             # 分析领域
│   │   ├── application/
│   │   │   ├── services/
│   │   │   │   ├── auth_service.py
│   │   │   │   ├── app_service.py
│   │   │   │   ├── rule_service.py
│   │   │   │   ├── rbac_service.py
│   │   │   │   └── analytics_service.py
│   │   │   └── dto/
│   │   ├── infrastructure/
│   │   │   ├── repositories/          # 数据仓储实现
│   │   │   ├── clickhouse/            # ClickHouse 查询构建器
│   │   │   ├── cache/                 # 权限缓存
│   │   │   └── external/              # 外部服务（威胁情报等）
│   │   └── interfaces/
│   │       └── http/
│   │           ├── v1/                # 保持 V1 兼容
│   │           └── v2/                # 新特性接口
│   ├── tests/
│   └── ...
│
├── worker/                            # 数据处理 Worker
│   ├── src/
│   │   ├── domain/
│   │   │   └── event/                 # 事件领域
│   │   ├── application/
│   │   │   ├── consumers/             # 消费者
│   │   │   ├── transformers/          # 转换器
│   │   │   └── writers/               # 写入器
│   │   ├── infrastructure/
│   │   │   ├── stream/                # Redis Stream
│   │   │   ├── clickhouse_batch/      # 批量写入
│   │   │   └── dead_letter/           # 死信队列
│   │   └── entrypoints/               # 启动入口
│   └── tests/
│
├── dashboard-ui/                      # Vue 3 前端
│   ├── src/
│   │   ├── api/
│   │   │   ├── modules/               # 按模块拆分 API
│   │   │   └── wrapper.js             # 统一 API 封装
│   │   ├── stores/                    # Pinia stores（替换 Vuex）
│   │   ├── components/
│   │   │   ├── common/                # 通用组件
│   │   │   └── business/              # 业务组件
│   │   ├── views/
│   │   │   ├── rules/
│   │   │   │   ├── VisualBuilder/     # 【新增】可视化规则编辑器
│   │   │   │   └── JsonEditor/        # JSON 编辑器
│   │   │   └── ...
│   │   ├── composables/               # 组合式函数
│   │   ├── utils/
│   │   └── router/
│   ├── tests/
│   └── ...
│
├── client-sdk/                        # 客户端 SDK
│   ├── src/
│   │   ├── core/
│   │   │   ├── collector/             # 采集器（支持缓存）
│   │   │   ├── behavior/              # 行为追踪
│   │   │   ├── engine.ts              # 主引擎
│   │   │   └── signer.ts              # 签名
│   │   ├── storage/
│   │   │   ├── base_driver.ts         # 【新增】抽象基类
│   │   │   ├── indexed_db.ts
│   │   │   ├── cookie.ts
│   │   │   ├── local_storage.ts
│   │   │   └── session_storage.ts
│   │   ├── cache/                     # 【新增】指纹缓存
│   │   └── utils/
│   ├── tests/
│   └── ...
│
├── adapters/                          # 场景适配器
│   ├── nginx-lua/
│   │   └── defense_v2.lua             # 使用 resty 标准库
│   ├── shopify/
│   │   ├── cloudflare_worker/         # 使用 KV 存储
│   │   └── theme_inject/
│   ├── wordpress/
│   └── website/
│
├── infrastructure/                    # 基础设施配置
│   ├── docker/
│   ├── kubernetes/
│   ├── nginx/
│   ├── monitoring/                    # Prometheus + Grafana
│   └── alerting/                      # 告警规则
│
├── tests/
│   ├── integration/                   # 集成测试
│   ├── e2e/                           # 端到端测试
│   └── performance/                   # 性能测试
│
├── docs/
│   ├── REWRITE_PLAN.md                # 本文档
│   ├── architecture/                  # 架构文档
│   ├── api/                           # API 文档
│   ├── modules/                       # 模块文档
│   └── deployment/                    # 部署文档
│
├── scripts/
│   ├── migration/                     # 数据迁移脚本
│   ├── dev/                           # 开发辅助脚本
│   └── deploy/                        # 部署脚本
│
├── docker-compose.yml                 # 本地开发环境
├── docker-compose.prod.yml            # 生产环境
├── Makefile                           # 常用命令
├── .env.example                       # 环境变量模板
├── .pre-commit-config.yaml            # Git hooks
├── pyproject.toml                     # Python 项目配置
└── README.md
```

---

## 三、分阶段重写实施计划

### 阶段一：基础设施与共享层（Week 1）

#### 1.1 shared/ 共享包（P0）

| 模块 | 目标 | 关键文件 | 交付物 |
|------|------|---------|-------|
| **event_normalizer** | 统一事件标准化 | `normalizer.py`、`constants.py`、`types.py` | 消除 admin/worker 双份代码 |
| **redis_manager** | 全局连接池 | `manager.py`、`config.py` | 连接池最大 100，socket_timeout=5s |
| **clickhouse_manager** | 参数化查询构建器 | `query_builder.py`、`client.py` | SQL 注入零风险 |
| **exceptions** | 业务异常体系 | `base.py`、`business.py`、`handlers.py` | 统一错误响应格式 |
| **logging** | 结构化日志 | `logger.py`、`formatters.py` | JSON 格式 + 上下文追踪 |
| **metrics** | Prometheus 指标 | `metrics.py`、`decorators.py` | 装饰器一键采集 |
| **schemas** | 跨服务 DTO | `event.py`、`decision.py`、`profile.py` | Pydantic v2 |
| **utils** | 工具函数 | `crypto.py`、`time.py`、`validators.py` | 单测覆盖 95% |

**核心设计——EventNormalizer**：

```python
# shared/event_normalizer/normalizer.py
from typing import Any
from .constants import DISPATCH_LABELS, IP_TYPE_LABELS
from .types import NormalizedEvent

class EventNormalizer:
    @staticmethod
    def normalize_timestamp_ms(value: Any) -> int | None: ...

    @staticmethod
    def normalize_dispatch_type(value: Any) -> str: ...

    @staticmethod
    def normalize_ip_type(value: Any) -> str: ...

    @classmethod
    def normalize(cls, entry: dict) -> NormalizedEvent:
        """事件标准化统一入口"""
```

**核心设计——RedisManager**：

```python
# shared/redis_manager/manager.py
from redis.asyncio import ConnectionPool, Redis

class RedisManager:
    _pool: ConnectionPool | None = None

    @classmethod
    async def init(cls, url: str, max_connections: int = 100) -> None: ...

    @classmethod
    async def get_client(cls) -> Redis: ...

    @classmethod
    async def close(cls) -> None: ...
```

**核心设计——ClickHouseQueryBuilder**：

```python
# shared/clickhouse_manager/query_builder.py
class ClickHouseQueryBuilder:
    def __init__(self, table: str): ...
    def select(self, *columns: str) -> "ClickHouseQueryBuilder": ...
    def where(self, condition: str, **params) -> "ClickHouseQueryBuilder": ...
    def order_by(self, column: str, desc: bool = False) -> "ClickHouseQueryBuilder": ...
    def limit(self, n: int) -> "ClickHouseQueryBuilder": ...
    def build(self) -> tuple[str, dict]: ...
```

#### 1.2 基础设施配置

- **docker-compose.yml**：Redis 7 + MySQL 8 + ClickHouse 23 + Nginx
- **pyproject.toml**：统一依赖管理（uv/poetry）
- **.pre-commit-config.yaml**：ruff + mypy + bandit
- **Makefile**：`make dev`、`make test`、`make lint`、`make build`

---

### 阶段二：Gateway API 决策引擎（Week 2）

#### 2.1 领域模型（domain/）

| 领域 | 实体 | 值对象 | 关键策略 |
|------|------|-------|---------|
| **decision** | `Decision`、`DecisionContext` | `RiskScore`、`Dispatch`、`Timing` | 决策优先级策略 |
| **profile** | `Profile` | `DeviceInfo`、`NetworkInfo`、`GeoInfo` | 特征丰富策略 |
| **rule** | `Rule`、`RuleSet` | `Condition`、`Action` | 规则匹配策略 |
| **risk** | `RiskAssessment` | `RiskLevel`、`Signal` | 五级流水线策略 |

#### 2.2 应用服务（application/services/）

**DecisionService（决策主流程）**：

```python
class DecisionService:
    def __init__(
        self,
        cache: DecisionCache,
        profile_builder: ProfileBuilder,
        precision_matcher: PrecisionMatcher,
        security_checker: SecurityChecker,
        risk_pipeline: RiskPipeline,
        disposition_resolver: DispositionResolver,
        event_publisher: EventPublisher,
    ): ...

    async def decide(self, request: DecideRequest) -> Decision:
        """
        决策流程（严格优先级）：
        1. 缓存查询          [< 5ms]
        2. 构建 Profile      [< 10ms]
        3. 精准规则匹配      [< 20ms] -> 命中即返回
        4. 安全检查          [< 5ms]
        5. 五级流水线打分    [< 15ms]
        6. 处置策略解析      [< 5ms]
        7. 缓存 + 异步事件   [异步]
        """
```

#### 2.3 基础设施实现（infrastructure/）

| 组件 | 实现要点 |
|------|---------|
| **DecisionCache** | Redis 缓存，TTL 60-300s，Key = `decision:v2:{site}:{device}` |
| **RuleRepository** | 规则热更新，本地 LRU + Redis Pub/Sub 失效通知 |
| **EventPublisher** | Redis Stream，批量发布，失败重试 |
| **MMDBReader** | GeoLite2，进程内缓存，惰性加载 |

#### 2.4 HTTP 接口层（interfaces/http/v2/）

- `POST /v2/decide`：完整决策（含流水线）
- `POST /v2/decide/fast`：快速决策（仅缓存 + 精准）
- `POST /v2/rule/test`：规则沙箱测试
- `GET /v2/metrics`：Prometheus 指标
- `GET /health`：健康检查

**中间件链**：
```
RequestID → Logging → Metrics → RateLimit → Auth → Handler
```

---

### 阶段三：Admin API 管理后台（Week 3）

#### 3.1 领域拆分

| 领域 | 职责 | 关键实体 |
|------|------|---------|
| **user** | 用户账户管理 | `User`、`Session`、`Token` |
| **app** | 应用配置管理 | `AppConfig`、`Snapshot`、`ApiKey` |
| **rule** | 规则 CRUD 与版本 | `Rule`、`RuleVersion`、`RuleTemplate` |
| **rbac** | 权限体系 | `Role`、`Permission`、`Policy` |
| **analytics** | 数据分析 | `AccessLog`、`Statistic`、`Report` |

#### 3.2 关键重构点落地

**① 权限缓存（消除 N+1）**

```python
# infrastructure/cache/permission_cache.py
class PermissionCache:
    async def get_user_permissions(self, user_id: str) -> set[str]:
        """请求级缓存 + Redis 缓存双层"""
        # L1: 请求上下文缓存
        # L2: Redis 缓存（TTL 5min）
        # L3: 数据库回源
```

**② 参数化 ClickHouse 查询**

```python
# infrastructure/clickhouse/access_log_repo.py
class AccessLogRepository:
    async def query_by_site(
        self, site_id: str, start: int, end: int, page: int, page_size: int
    ) -> list[AccessLog]:
        query, params = (
            ClickHouseQueryBuilder("access_logs")
            .select("*")
            .where("site_id = %(site_id)s", site_id=site_id)
            .where("timestamp BETWEEN %(start)s AND %(end)s", start=start, end=end)
            .order_by("timestamp", desc=True)
            .limit(page_size)
            .build()
        )
        return await self.client.execute(query, params)
```

**③ 函数拆分示例（get_sdk_test_context）**

```python
# application/services/app_service.py
class AppService:
    async def get_sdk_test_context(self, app_id: str, user: User) -> SdkTestContext:
        app = await self._fetch_and_validate(app_id, user)
        snapshot = await self._load_snapshot(app)
        return SdkTestContext(
            access=await self._build_access_info(app),
            site=await self._build_site_info(app),
            snapshot=await self._build_snapshot_info(app, snapshot),
            rules=await self._build_rules_info(snapshot),
            intelligence=await self._build_intelligence_info(snapshot),
        )
    # 每个私有方法 < 30 行
```

#### 3.3 HTTP 接口层

- `v1/*`：**保留 V1 契约**，仅实现改造（保证前端兼容）
- `v2/*`：新特性接口（规则版本、模板、可视化配置等）

---

### 阶段四：Worker 数据处理（Week 3-4）

#### 4.1 领域与应用层

| 层次 | 组件 | 职责 |
|------|------|------|
| Domain | `Event` | 事件实体、状态机 |
| Application | `StreamConsumer` | 消费 Redis Stream |
| Application | `EventTransformer` | 使用 `shared/event_normalizer` |
| Application | `BatchWriter` | ClickHouse 批量写入 |
| Application | `DeadLetterHandler` | 死信队列处理 |

#### 4.2 关键改进

**① 部分失败处理**

```python
class BatchWriter:
    async def write(self, batch: list[NormalizedEvent]) -> WriteResult:
        try:
            await self._write_batch(batch)
            return WriteResult(success=len(batch), failed=[])
        except Exception:
            # 批量失败 → 逐条尝试
            failed = []
            for event in batch:
                try:
                    await self._write_single(event)
                except Exception as e:
                    failed.append((event, str(e)))
                    await self._dlq.send(event, str(e))
            return WriteResult(success=len(batch) - len(failed), failed=failed)
```

**② 指数退避重试**

```python
class RetryPolicy:
    async def execute(self, func, *args, max_retries=3):
        for attempt in range(max_retries):
            try:
                return await func(*args)
            except RetryableError:
                await asyncio.sleep(2 ** attempt)
```

**③ 精细化异常处理**

```python
class StreamConsumer:
    async def consume(self):
        try:
            events = await self._read_stream()
        except RedisConnectionError:
            # 可恢复：等待重连
            await self._reconnect()
        except ParseError as e:
            # 不可恢复：入死信
            await self._dlq.send_raw(e.raw_data, str(e))
```

---

### 阶段五：前端 Dashboard UI（Week 5）

#### 5.1 技术栈升级

| 项 | V1 | V2 |
|----|----|----|
| 状态管理 | Vuex | **Pinia** |
| 路由 | vue-router 3 | vue-router 4 |
| 组件库 | Element UI | Naive UI |
| 构建 | Webpack | **Vite** |
| 类型 | JavaScript | **TypeScript** |

#### 5.2 API 层封装

```typescript
// src/api/wrapper.ts
export function createApi<TArgs extends unknown[], TData>(
  configFn: (...args: TArgs) => AxiosRequestConfig
) {
  return async (...args: TArgs): Promise<ApiResult<TData>> => {
    try {
      const { data } = await request(configFn(...args));
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: normalizeError(error),
        code: error.response?.status,
      };
    }
  };
}

// src/api/modules/apps.ts
export const getApps = createApi<[AppListParams], AppListResponse>((params) => ({
  method: 'get',
  url: '/v2/apps',
  params,
}));
```

#### 5.3 Pinia Store 设计

```typescript
// src/stores/user.ts
export const useUserStore = defineStore('user', {
  state: () => ({ user: null, permissions: [], token: null }),
  getters: {
    isSuperUser: (state) => state.user?.is_super_user ?? false,
    hasPermission: (state) => (code: string) =>
      state.permissions.includes(code) || state.isSuperUser,
  },
  actions: {
    async login(username: string, password: string) {
      const { data } = await loginApi(username, password);
      this.token = data.access_token;
      await Promise.all([this.fetchProfile(), this.fetchPermissions()]);
    },
  },
});
```

#### 5.4 规则可视化编辑器（新增）

**目录结构**：
```
views/rules/VisualBuilder/
├── index.vue                    # 主入口（支持 JSON/可视化切换）
├── components/
│   ├── ConditionGroup.vue       # 条件组（AND/OR）
│   ├── ConditionRow.vue         # 单条条件
│   ├── FieldSelector.vue        # 字段选择器（含类型推断）
│   ├── OperatorSelector.vue     # 操作符选择器
│   ├── ValueInput.vue           # 值输入（自适应类型）
│   └── ActionSelector.vue       # 动作选择器
├── composables/
│   ├── useRuleBuilder.ts        # 规则构建逻辑
│   ├── useRuleValidator.ts      # 规则校验
│   └── useJsonSync.ts           # JSON ↔ 可视化双向同步
└── schemas/
    └── field_registry.ts        # 字段元数据注册表
```

---

### 阶段六：Client SDK 重写（Week 5）

#### 6.1 存储驱动抽象

```typescript
// src/storage/base_driver.ts
export abstract class BaseStorageDriver implements StorageDriver {
  abstract readonly name: string;
  protected initialized = false;

  protected abstract init(): Promise<void>;
  protected abstract getInternal(key: string): Promise<string | null>;
  protected abstract setInternal(key: string, value: string): Promise<void>;
  protected abstract removeInternal(key: string): Promise<void>;

  private async ensureInitialized(): Promise<void> {
    if (!this.initialized) {
      await this.init();
      this.initialized = true;
    }
  }

  async get(key: string): Promise<string | null> {
    try {
      await this.ensureInitialized();
      return await this.getInternal(key);
    } catch (error) {
      this.logError('get', error);
      return null;
    }
  }
  // set/remove 同理
}
```

#### 6.2 指纹缓存

```typescript
// src/cache/fingerprint_cache.ts
export class FingerprintCache {
  private cache: FingerprintData | null = null;
  private lastCollectTime = 0;
  private inflight: Promise<FingerprintData> | null = null;

  constructor(private ttl = 5 * 60 * 1000) {}

  async getOrCollect(options: CollectOptions): Promise<FingerprintData> {
    const now = Date.now();

    if (this.cache && now - this.lastCollectTime < this.ttl && !options.forceRefresh) {
      return this.cache;
    }
    if (this.inflight) return this.inflight;

    this.inflight = this.collect(options);
    try {
      this.cache = await this.inflight;
      this.lastCollectTime = now;
      return this.cache;
    } finally {
      this.inflight = null;
    }
  }
}
```

---

### 阶段七：Adapters 场景适配器（Week 6）

#### 7.1 Nginx Lua 优化

```lua
-- adapters/nginx-lua/defense_v2.lua
local resty_hmac = require "resty.hmac"
local resty_string = require "resty.string"
local cjson = require "cjson.safe"

local M = {}

function M.generate_sign(params, api_key)
    local keys = {}
    for k in pairs(params) do table.insert(keys, k) end
    table.sort(keys)

    local parts = {}
    for _, k in ipairs(keys) do
        parts[#parts + 1] = ngx.escape_uri(k) .. "=" .. ngx.escape_uri(tostring(params[k]))
    end
    local qs = table.concat(parts, "&")

    local hmac = resty_hmac:new(api_key, resty_hmac.ALGOS.SHA256)
    hmac:update(qs)
    return resty_string.to_hex(hmac:final())
end

return M
```

#### 7.2 Cloudflare Worker 分布式限流

```javascript
// adapters/shopify/cloudflare_worker/rate_limiter.js
export async function checkRateLimit(env, key, maxRequests = 100, windowSec = 60) {
  const now = Date.now();
  const cacheKey = `rl:${key}`;

  const record = (await env.FANGYU_KV.get(cacheKey, 'json')) || {
    count: 0,
    resetAt: now + windowSec * 1000,
  };

  if (now > record.resetAt) {
    record.count = 0;
    record.resetAt = now + windowSec * 1000;
  }

  if (record.count >= maxRequests) return { allowed: false, resetAt: record.resetAt };

  record.count++;
  await env.FANGYU_KV.put(cacheKey, JSON.stringify(record), { expirationTtl: windowSec });
  return { allowed: true, remaining: maxRequests - record.count };
}
```

---

## 四、技术栈说明

### 4.1 后端技术栈

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| Python | CPython | 3.11+ | 支持 asyncio TaskGroup |
| Web 框架 | FastAPI | 0.109+ | Pydantic v2 |
| ORM | SQLAlchemy 2.0 + Alembic | 2.0+ | 替换 Tortoise（生态更成熟） |
| ClickHouse Driver | clickhouse-driver + async-clickhouse | latest | 异步支持 |
| Redis | redis-py | 5.0+ | 官方异步 |
| 验证 | Pydantic | v2 | 高性能 |
| 依赖管理 | uv 或 poetry | latest | 快速 |
| 日志 | structlog | 24+ | 结构化 |
| 监控 | prometheus-client | latest | 官方 |
| 测试 | pytest + pytest-asyncio | latest | 异步测试 |

### 4.2 前端技术栈

| 组件 | 选型 | 版本 |
|------|------|------|
| 框架 | Vue | 3.4+ |
| 语言 | TypeScript | 5.3+ |
| 状态 | Pinia | 2.1+ |
| 路由 | vue-router | 4.2+ |
| UI 库 | Naive UI | 2.36+ |
| 构建 | Vite | 5.0+ |
| 图表 | ECharts | 5.4+ |
| 编辑器 | Monaco Editor | 0.44+ |
| HTTP | Axios | 1.6+ |
| 测试 | Vitest + Playwright | latest |

### 4.3 基础设施

- Docker + Docker Compose（本地）
- Kubernetes（生产可选）
- Nginx / OpenResty（边缘）
- Prometheus + Grafana（监控）
- Loki（日志聚合）

---

## 五、六周实施时间表

| 周次 | 阶段 | 主要任务 | 关键交付物 | 里程碑 |
|------|------|---------|-----------|--------|
| **W1** | 基础设施 | shared/ 全部模块、docker-compose、CI 骨架 | 8 个共享包 + 单测覆盖 90% | ✅ 基础层就绪 |
| **W2** | Gateway 引擎 | domain + application + infrastructure + interfaces | `/v2/decide` `/v2/decide/fast` | ✅ 决策引擎 MVP |
| **W3** | Admin API | 5 大领域重写 + V1 兼容层 + V2 新接口 | admin-api 完整功能 | ✅ 后台可用 |
| **W3-W4** | Worker | 消费者 + 转换器 + 批量写入 + 死信 | worker 完整功能 | ✅ ETL 就绪 |
| **W5** | 前端 + SDK | Pinia 迁移、可视化编辑器、SDK 缓存 | dashboard-ui + client-sdk | ✅ UI/SDK 就绪 |
| **W6** | Adapters + 集成 | 4 个 adapter + E2E 测试 + 灰度切换 | 全链路可用 + 压测报告 | ✅ 生产就绪 |

**每周节奏**：
- Mon-Tue：编码
- Wed：代码审查 + 联调
- Thu-Fri：测试 + 修复
- 周末：文档 + 复盘

---

## 六、质量保障方案

### 6.1 测试金字塔

```
        ┌───────────┐
        │  E2E 5%   │ 关键业务流程
        ├───────────┤
        │ Integ 25% │ 服务间集成
        ├───────────┤
        │Unit  70%  │ 领域 + 应用层
        └───────────┘
```

**覆盖率要求**：
- 领域层（domain）：≥ 95%
- 应用层（application）：≥ 85%
- 基础设施层（infrastructure）：≥ 75%
- 接口层（interfaces）：≥ 70%
- **整体**：≥ 80%

### 6.2 代码质量门禁

**CI 流水线（提交即触发）**：
1. `ruff check` + `ruff format --check`
2. `mypy --strict`
3. `bandit -r src/ -ll`
4. `pytest --cov --cov-fail-under=80`
5. Docker 构建 + 镜像大小检查（< 200MB）
6. SonarQube 扫描（可选）

**代码规范**：
- 单函数 ≤ 50 行
- 单文件 ≤ 500 行
- 圈复杂度 ≤ 10
- 类型注解覆盖率 ≥ 95%

### 6.3 性能基准

**Gateway API**：
| 指标 | 目标 |
|------|------|
| P50 延迟 | < 25ms |
| P95 延迟 | < 50ms |
| P99 延迟 | < 80ms |
| QPS（单实例） | ≥ 3000 |
| 缓存命中率 | ≥ 85% |
| CPU（P95） | ≤ 70% |

**压测方案**：
- 工具：Locust（Python）+ k6（Go 场景）
- 数据集：真实业务样本 10 万条
- 场景：80% 缓存命中 + 20% 未命中
- 时长：30 分钟稳定测试

### 6.4 灰度发布策略

```
Day 1-3   ▶ 内部测试环境
Day 4-7   ▶ 预发环境（影子流量）
Day 8-10  ▶ 生产 10% 流量
Day 11-14 ▶ 生产 50% 流量
Day 15+   ▶ 生产 100% 流量（保留 V1 备份 30 天）
```

**回滚阈值**：
- 错误率 > 1% 持续 5 分钟 → 自动回滚
- P95 延迟 > 100ms 持续 10 分钟 → 告警
- 缓存命中率 < 70% 持续 10 分钟 → 告警

### 6.5 监控告警

**核心指标（Prometheus）**：
- `decision_requests_total{site_id, result}`
- `decision_latency_seconds_bucket{site_id, cached}`
- `cache_hit_rate{cache_type}`
- `rule_hits_total{rule_id}`
- `event_lag_seconds`（Worker 消费滞后）

**告警规则**：
- 错误率 > 1% → Critical
- P95 延迟 > 100ms → Warning
- 缓存命中率 < 70% → Warning
- Worker 消费滞后 > 60s → Warning
- Redis/MySQL 不可用 → Critical

---

## 七、数据迁移与兼容性

### 7.1 数据迁移路径

| 数据源 | 迁移方式 | 工具 |
|--------|---------|------|
| MySQL 配置表 | Alembic 迁移脚本 | `scripts/migration/mysql_migrate.py` |
| ClickHouse 日志 | 双写 + 逐步切读 | `scripts/migration/ch_dual_write.py` |
| Redis 缓存 | 冷启动预热 | `scripts/migration/cache_warmup.py` |

### 7.2 API 契约兼容

- `/v1/*`：**100% 兼容** V1 请求/响应
- `/v2/*`：新特性接口
- Response 结构升级采用 `application/vnd.fangyu.v2+json` MIME 版本控制

### 7.3 灰度切换

**流量切换（Nginx 层）**：
```nginx
upstream gateway_v1 { server v1:8000; }
upstream gateway_v2 { server v2:8000; }

split_clients "$request_id" $backend {
    10%     gateway_v2;   # 灰度 10%
    *       gateway_v1;   # 剩余走 V1
}

location /decide {
    proxy_pass http://$backend;
}
```

---

## 八、风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 业务逻辑对齐偏差 | 中 | 高 | 建立 V1/V2 对比测试集，回归 10 万样本 |
| 性能不达预期 | 低 | 高 | Week 2 结束即启动压测，持续调优 |
| 依赖生态问题 | 低 | 中 | 关键依赖锁定版本 + 自建镜像 |
| 团队学习成本 | 中 | 中 | 提前技术分享（DDD、Pinia、SQLAlchemy 2.0） |
| 灰度发现严重问题 | 低 | 高 | 5 分钟内可回滚 + 保留 V1 30 天 |

---

## 九、目录初始化清单（Week 1 Day 1）

在 `Evercookie Defense System V2/` 下创建：

```bash
mkdir -p shared/{event_normalizer,redis_manager,clickhouse_manager,exceptions,logging,metrics,schemas,utils}
mkdir -p gateway-api/{src/{domain,application,infrastructure,interfaces},tests,config}
mkdir -p admin-api/{src/{domain,application,infrastructure,interfaces},tests,config}
mkdir -p worker/{src/{domain,application,infrastructure,entrypoints},tests,config}
mkdir -p dashboard-ui/{src/{api,stores,components,views,composables,utils,router},tests,public}
mkdir -p client-sdk/{src/{core,storage,cache,utils},tests,examples}
mkdir -p adapters/{nginx-lua,shopify,wordpress,website}
mkdir -p infrastructure/{docker,kubernetes,nginx,monitoring,alerting}
mkdir -p tests/{integration,e2e,performance}
mkdir -p docs/{architecture,api,modules,deployment}
mkdir -p scripts/{migration,dev,deploy}
```

各服务根目录初始化文件：
- `pyproject.toml`（Python 项目）
- `Dockerfile`
- `README.md`
- `.env.example`

---

## 十、成功标准

**功能标准**：
- ✅ V1 全部功能在 V2 可用
- ✅ V1 API 契约 100% 兼容
- ✅ V2 新增：可视化规则编辑器、规则版本、规则模板、规则沙箱

**性能标准**：
- ✅ Gateway P95 延迟 < 50ms（V1 是 650ms）
- ✅ 单实例 QPS ≥ 3000（V1 是 300）
- ✅ 缓存命中率 ≥ 85%
- ✅ CPU 使用率 ≤ 70%

**质量标准**：
- ✅ 测试覆盖率 ≥ 80%
- ✅ 代码重复率 < 5%（V1 约 30%）
- ✅ 无高危安全漏洞（Bandit + Trivy 扫描）
- ✅ 平均函数行数 ≤ 35

**运维标准**：
- ✅ 一键启动本地环境（`make dev`）
- ✅ CI/CD 全流程自动化
- ✅ 生产回滚 < 5 分钟
- ✅ 监控覆盖核心指标

---

## 十一、后续行动

**本计划批准后立即执行**：

1. 【立即】创建 V2 根目录及骨架结构（脚本已提供）
2. 【Day 1】初始化 `shared/` 8 个包，编写 `event_normalizer` 首个模块
3. 【Day 2】完成 `redis_manager` + `clickhouse_manager` + `exceptions`
4. 【Day 3】完成 `logging` + `metrics` + `schemas` + `utils`
5. 【Day 4-5】补齐单测（覆盖率 ≥ 90%），Week 1 收官

**每周固定动作**：
- 周一：Kick-off 明确任务
- 周三：Code Review Session
- 周五：Demo + 回顾

---

**文档结束** | 版本 V2.0 | 最后更新 2026-07-31
