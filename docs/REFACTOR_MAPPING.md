# V1 → V2 重构点映射表

**用途**: 明确每个 V1 问题在 V2 中的落地位置，作为重写时的对照清单

---

## 图例
- 🔴 P0（安全/严重性能）
- 🟠 P1（架构/中等性能）
- 🟡 P2（可维护性）
- ⚪ P3（优化）

---

## 一、后端重构点映射

### 1.1 代码冗余类

| # | 优先级 | V1 位置 | V1 问题 | V2 落地位置 | V2 方案 |
|---|--------|---------|---------|-------------|---------|
| 1 | 🔴 P0 | `admin-api/app/core/access_event_service.py` L32-85<br>`worker/event_transformer.py` L32-85 | 事件标准化逻辑重复 500+ 行 | `shared/event_normalizer/` | 提取 `EventNormalizer` 单一入口，admin/worker 共同依赖 |
| 2 | 🟠 P1 | `admin-api/app/core/clickhouse_client.py`<br>`worker/clickhouse_batch.py` | ClickHouse 客户端重复初始化 | `shared/clickhouse_manager/` | `ClickHouseClient` 单例 + 参数化查询构建器 |
| 3 | ⚪ P3 | `client-sdk/src/storage/*.ts` | 每个存储驱动重复实现初始化和错误处理 | `client-sdk/src/storage/base_driver.ts` | 抽象基类 `BaseStorageDriver` |

### 1.2 性能问题类

| # | 优先级 | V1 位置 | V1 问题 | V2 落地位置 | V2 方案 |
|---|--------|---------|---------|-------------|---------|
| 4 | 🔴 P0 | `admin-api/app/core/rbac.py` L15-30, L42-59 | 权限检查 N+1 查询 | `admin-api/src/infrastructure/cache/permission_cache.py` | 双层缓存（请求级 + Redis） |
| 5 | 🟠 P1 | `admin-api/app/core/access_event_service.py` L338-363 | Redis 连接未池化 | `shared/redis_manager/` | 全局 `ConnectionPool` 单例 |
| 6 | 🟠 P1 | `worker/clickhouse_batch.py` L249-303 | 批量写入无部分失败处理 | `worker/src/application/writers/batch_writer.py` | 逐条降级 + 死信队列 + 指数退避 |
| 7 | ⚪ P3 | `client-sdk/src/core/collector.ts` L289-306 | 指纹采集无缓存 | `client-sdk/src/cache/fingerprint_cache.ts` | `FingerprintCache` + inflight 防抖 |

### 1.3 安全问题类

| # | 优先级 | V1 位置 | V1 问题 | V2 落地位置 | V2 方案 |
|---|--------|---------|---------|-------------|---------|
| 8 | 🔴 P0 | `admin-api/app/core/clickhouse_client.py` L92-111, L134-149 | SQL 拼接注入风险 | `shared/clickhouse_manager/query_builder.py` | 参数化 `ClickHouseQueryBuilder` |
| 9 | 🟡 P2 | `admin-api/app/config.py` L12-33 | `_DEV_SECRETS` 全局变量线程不安全 | `shared/utils/secrets.py` | 使用 Pydantic `SecretStr` + `field_validator` |
| 10 | 🟡 P2 | `adapters/shopify/cloudflare_worker.js` L73-80 | Worker 全局变量误用 | `adapters/shopify/cloudflare_worker/rate_limiter.js` | Cloudflare KV 分布式限流 |

### 1.4 架构问题类

| # | 优先级 | V1 位置 | V1 问题 | V2 落地位置 | V2 方案 |
|---|--------|---------|---------|-------------|---------|
| 11 | 🟠 P1 | `gateway-api/app/api/v1/decide.py`（1752 行）<br>`gateway-api/app/core/disposition.py`<br>`gateway-api/app/core/evaluator.py` | 决策逻辑分散在 3 个文件 | `gateway-api/src/application/services/decision_service.py` | 统一 `DecisionService` 编排 |
| 12 | 🟠 P1 | 无对应模块 | 缺少缓存机制 | `gateway-api/src/infrastructure/cache/decision_cache.py` | Redis 决策缓存（TTL 60-300s） |
| 13 | 🟠 P1 | 无对应模块 | 缺少规则预编译 | `gateway-api/src/infrastructure/rule_repo/compiler.py` | 启动时预编译规则 AST |

### 1.5 可维护性类

| # | 优先级 | V1 位置 | V1 问题 | V2 落地位置 | V2 方案 |
|---|--------|---------|---------|-------------|---------|
| 14 | 🟡 P2 | `admin-api/app/api/v1/apps.py` L873-1009 | `get_sdk_test_context` 137 行 | `admin-api/src/application/services/app_service.py` | 拆为 5 个私有方法（每个 ≤ 30 行） |
| 15 | 🟡 P2 | `admin-api/app/core/access_event_service.py` L226-335 | `normalize_event` 110 行 | `shared/event_normalizer/normalizer.py` | 拆为字段级 + 汇总方法 |
| 16 | 🟡 P2 | `adapters/nginx-lua/defense.lua` L543-632 | `run` 函数 90 行 | `adapters/nginx-lua/defense_v2.lua` | 拆为 pre_check、build_context、call_gateway、post_process |
| 17 | 🟡 P2 | admin-api 多处 `except Exception` | 异常处理粗暴，掩盖真实错误 | `shared/exceptions/` | 分层异常体系 + 精细捕获 |
| 18 | 🟡 P2 | `worker/consumer.py` L23-52 | 消费者异常处理粗暴 | `worker/src/application/consumers/stream_consumer.py` | 区分 `RetryableError` / `NonRetryableError` |

### 1.6 Lua/JS 优化类

| # | 优先级 | V1 位置 | V1 问题 | V2 落地位置 | V2 方案 |
|---|--------|---------|---------|-------------|---------|
| 19 | ⚪ P3 | `adapters/nginx-lua/defense.lua` L140-177 | 手写 HMAC-SHA256 | `adapters/nginx-lua/defense_v2.lua` | 使用 `lua-resty-string` + `resty.hmac` |

---

## 二、前端重构点映射

| # | 优先级 | V1 位置 | V1 问题 | V2 落地位置 | V2 方案 |
|---|--------|---------|---------|-------------|---------|
| 20 | 🟡 P2 | `dashboard-ui/src/api/apps.js` | API 无统一错误处理 | `dashboard-ui/src/api/wrapper.ts` | `createApi()` 高阶函数封装 |
| 21 | 🟡 P2 | `dashboard-ui/src/store/modules/user/index.js` | Vuex login 职责过多 | `dashboard-ui/src/stores/user.ts` | Pinia store，`login` 自动加载 profile/permissions |
| 22 | 🟠 P1 | `dashboard-ui/src/views/rules/` | 仅 JSON 编辑器 | `dashboard-ui/src/views/rules/VisualBuilder/` | 可视化 + JSON 双模式 |

---

## 三、共享包与新增模块清单

### 3.1 新增共享包（shared/）

| 包名 | 消除的问题 | 新价值 |
|------|-----------|-------|
| `event_normalizer` | 问题 1 | 一处修改，处处生效 |
| `redis_manager` | 问题 5 | 连接复用，性能翻倍 |
| `clickhouse_manager` | 问题 2、8 | 安全 + 复用 |
| `exceptions` | 问题 17 | 统一错误响应 |
| `logging` | - | 结构化日志、请求追踪 |
| `metrics` | - | 可观测性 |
| `schemas` | - | 跨服务契约 |
| `utils` | 问题 9 | 通用工具 |

### 3.2 新增基础设施模块

| 模块 | 消除的问题 | 新价值 |
|------|-----------|-------|
| `gateway-api/src/infrastructure/cache/decision_cache.py` | 问题 12 | P95 延迟 650ms → 50ms |
| `gateway-api/src/infrastructure/rule_repo/compiler.py` | 问题 13 | 规则匹配提速 5x |
| `admin-api/src/infrastructure/cache/permission_cache.py` | 问题 4 | 权限检查提速 3x |
| `worker/src/application/writers/batch_writer.py` | 问题 6 | 部分失败可恢复 |
| `client-sdk/src/storage/base_driver.ts` | 问题 3 | 存储驱动去重 |
| `client-sdk/src/cache/fingerprint_cache.ts` | 问题 7 | 采集延迟 3s → 0ms |
| `adapters/shopify/cloudflare_worker/rate_limiter.js` | 问题 10 | 分布式限流 |
| `adapters/nginx-lua/defense_v2.lua` | 问题 16、19 | Lua 代码质量 |

### 3.3 新增业务模块

| 模块 | 说明 |
|------|------|
| `gateway-api/src/application/services/decision_service.py` | 统一决策编排 |
| `gateway-api/src/application/services/precision_matcher.py` | 精准规则匹配 |
| `gateway-api/src/application/services/disposition_resolver.py` | 处置策略解析 |
| `admin-api/src/application/services/app_service.py` | 应用配置管理 |
| `admin-api/src/application/services/rule_service.py` | 规则 CRUD + 版本 |
| `admin-api/src/application/services/rbac_service.py` | 权限管理 |
| `worker/src/application/consumers/stream_consumer.py` | Stream 消费 |
| `dashboard-ui/src/views/rules/VisualBuilder/` | 可视化规则编辑器 |

---

## 四、实施顺序（Kanban）

### Sprint 1（Week 1）—— 基础层
- [ ] 问题 1: `shared/event_normalizer/`
- [ ] 问题 2, 8: `shared/clickhouse_manager/`
- [ ] 问题 5: `shared/redis_manager/`
- [ ] 问题 17: `shared/exceptions/`
- [ ] 补齐 shared 其他 4 个包
- [ ] 单测覆盖率 ≥ 92%

### Sprint 2（Week 2）—— Gateway
- [ ] 问题 11: `DecisionService` 统一编排
- [ ] 问题 12: `DecisionCache`
- [ ] 问题 13: 规则预编译
- [ ] `/v2/decide` `/v2/decide/fast` 接口
- [ ] 单实例压测：P95 < 50ms

### Sprint 3（Week 3）—— Admin API
- [ ] 问题 4: `PermissionCache`
- [ ] 问题 8: 全部查询改造为参数化
- [ ] 问题 14, 15: 超长函数拆分
- [ ] V1 兼容层 + V2 新接口

### Sprint 4（Week 3-4）—— Worker
- [ ] 问题 6: 部分失败处理
- [ ] 问题 18: 精细化异常
- [ ] 死信队列
- [ ] 消费滞后监控

### Sprint 5（Week 5）—— 前端 + SDK
- [ ] 问题 20: API 封装
- [ ] 问题 21: Vuex → Pinia 迁移
- [ ] 问题 22: 可视化规则编辑器
- [ ] 问题 3: 存储驱动抽象
- [ ] 问题 7: 指纹缓存

### Sprint 6（Week 6）—— Adapters + 集成
- [ ] 问题 16, 19: Lua v2
- [ ] 问题 10: Cloudflare KV 限流
- [ ] E2E 测试
- [ ] 灰度发布

---

## 五、验收标准（每个问题）

每个重构点必须提供：

1. **代码位置明确**：新文件路径 + 类/方法名
2. **单测覆盖**：≥ 80%
3. **性能验证**：相关指标压测数据
4. **对比测试**：与 V1 输出对比（≥ 10000 样本）
5. **文档更新**：`docs/modules/` 对应模块说明

---

**文档结束**
