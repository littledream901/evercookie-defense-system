# Evercookie Defense System V2 项目设计文档

| 项 | 内容 |
|----|------|
| 文档版本 | 1.0 |
| 系统版本 | V2.0.0（App-Site 双层架构，即内部代号 V3 数据模型） |
| 文档状态 | 定稿，可用于指导开发与测试 |
| 适用范围 | gateway-api / admin-api / worker / shared / dashboard-ui / client-sdk / adapters |
| 编写依据 | 仓库现有代码、Alembic 迁移、ClickHouse DDL、部署编排与既有设计文档 |

> 本文档所有技术结论均来自对当前仓库的实际核对。凡与代码现状存在差异的部分，统一在 [第 8 章 已知技术债与收敛计划](#8-已知技术债与收敛计划) 中显式列出，不在正文中掩盖。

---

## 1. 项目概述

### 1.1 项目定位

Evercookie Defense System（内部代号 fangyu / 防御）是一套**面向多站点的实时流量风险决策与处置平台**。它部署在业务站点的流量入口处，对每一次访问请求在毫秒级内给出「是否可信、如何处置、处置到哪里」的结论，并把决策全过程落库供运营复盘与策略调优。

系统不是单纯的 WAF，也不是单纯的验证码服务，其差异化定位体现在三点：

1. **持久化访客识别**：通过 Evercookie 六通道（Cookie / localStorage / sessionStorage / IndexedDB / window.name / CacheStorage）投票与自愈机制维持访客身份，对抗常规清理手段，使「同一访客的历史行为」成为可用的决策输入。
2. **正交三层处置模型**：将「裁决（为什么）× 机制（怎么做）× 目标（去哪）」拆为三个独立维度，支持放行、投放替代页、单地址/地址池跳转、人机挑战、拒绝、静默 404 等组合，而非固化的黑白名单二元结果。
3. **双层接入架构**：服务端适配器（第一层）在 HTML 下发之前完成拦截，客户端 SDK（第二层）用真实浏览器指纹二次校验，两层通过一次性 serverToken 形成闭环。

### 1.2 建设目标

| 维度 | V1 现状 | V2 目标 | 达成手段 |
|------|---------|---------|----------|
| P95 决策时延 | 650 ms | < 50 ms | 决策缓存 + Redis 读取面 + 进程内二级缓存 |
| 单实例 QPS | 1 000 | ≥ 10 000 | 全异步栈 + 事件旁路写入 + 无状态网关横向扩展 |
| 决策缓存命中率 | 0% | ≥ 85% | `(site_id, fingerprint, ip)` 三元组键 + 分机制 TTL |
| 业务隔离粒度 | 单层站点 | 应用 + 站点两层 | `biz_application` / `biz_site` 拆分 |
| 核心模块测试覆盖率 | ~45% | ≥ 80% | DDD 四层分层 + 依赖注入 + 契约测试 |
| 单文件规模 | 1000+ 行 | ≤ 500 行 | 领域下沉，应用层仅做编排 |

### 1.3 核心业务价值

- **降低恶意流量成本**：对数据中心 IP、代理/VPN、安全扫描器、AI 爬虫等实施差异化处置，避免全量走验证码带来的正常访客流失。
- **保护高价值页面**：`money_page` 类页面（结算、后台、敏感路径）可配置为服务端层直接拦截，恶意流量拿不到 HTML 正文。
- **可解释的风控**：每次决策落库 `decided_by` / `decided_stage` / `decided_rule_id` / `scorer_scores` / `condition_traces`，运营可回答「这个访客为什么被拦」，而非只看到一个分数。
- **策略可灰度**：规则支持 `shadow` 影子状态，先观测影响面再发布，避免策略变更直接冲击线上。
- **多站点统一治理**：一个应用下的多个站点共享密钥信任根与应用级规则，同时保留站点级差异化配置。

### 1.4 Stakeholders 与权责

| 角色 | 系统内角色码 | 核心诉求 | 主要交互界面 |
|------|-------------|---------|-------------|
| 平台超级管理员 | `super_admin`（权限 `*`） | 系统初始化、用户与角色治理、全局兜底配置 | dashboard-ui 全部模块 |
| 业务管理员 | `admin` | 应用/站点全生命周期、规则发布、情报维护 | 应用、站点、规则、情报、分析 |
| 安全运营 | `operator` | 规则调优、封禁与白名单处置、阈值调整 | 规则、频控、白名单、访问日志 |
| 审计人员 | `auditor`（全部只读） | 操作留痕核查、合规取证 | 审计日志、访问日志、分析 |
| 站点接入方（外部） | 无后台账号，持 `site_key` | 低侵入接入、失败不影响业务 | adapters / client-sdk |
| 平台研发与 SRE | 无系统角色 | 可观测性、部署可回滚、故障可定位 | Prometheus / Grafana / 诊断接口 |

---

## 2. 业务架构设计（App-Site 双层结构）

### 2.1 双层业务模型概览

系统采用 **Application（应用）→ Site（站点）** 两层业务架构，替代 V1 的单层 Application 模型。此架构对应企业实际场景：一个企业（或一个产品线）旗下往往有多个域名站点，它们共享统一的安全策略、密钥信任根与运营团队，但各自有独立的域名、接入方式与运行时配置。

```
┌─────────────────────────────────────────────────────────┐
│  Application 层（应用/业务分组）                           │
│  - app_key:     app_abc12345                            │
│  - app_secret:  统一密钥信任根                            │
│  - owner:       业务归属                                  │
│  - 应用级规则:   继承到所有子站点                          │
│  - 评分配置:     全局阈值与权重                            │
├─────────────────────────────────────────────────────────┤
│  ├─ Site A (站点 1)                                      │
│  │  - site_key:   site_xyz789 (X-App-Key 请求头)        │
│  │  - domain:     shop.example.com                      │
│  │  - access_mode: adapter (Nginx/CF Worker)            │
│  │  - 站点级规则:  仅作用于本站点                          │
│  │                                                       │
│  ├─ Site B (站点 2)                                      │
│  │  - site_key:   site_def456                           │
│  │  - domain:     blog.example.com                      │
│  │  - access_mode: sdk (纯浏览器)                        │
│  │                                                       │
│  └─ Site C (站点 3) ...                                 │
└─────────────────────────────────────────────────────────┘
```

### 2.2 应用层职责边界（核心层能力）

应用层是**业务归属与统一策略的承载单元**，对应「一个企业主体」或「一个产品线」。其核心能力：

| 能力 | 实现方式 | 业务意义 |
|------|---------|---------|
| **密钥信任根** | `app_secret`（128 字符）| HMAC 验签密钥，所有子站点共享。站点级 `site_secret` 为可选增强 |
| **业务归属** | `owner_user_id` → `sys_user.id` | 明确该应用由哪位管理员负责，权限委托的起点 |
| **统一规则继承** | `biz_rule.app_id` + `inherit_from_app` | 应用级规则自动对所有子站点生效，无需逐站点绑定 |
| **评分配置** | `biz_scoring_config.app_id` | challenge / block 阈值与 7 个 scorer 权重在应用级统一，避免各站点阈值分裂 |
| **活跃开关** | `is_active` | 停用应用时子站点一并停用（级联生效） |

**隔离语义**：不同应用的流量在决策、画像、频控、日志分析各层面完全隔离。ClickHouse `decision_events` 的 `ORDER BY (app_id, ...)` 前缀分区键确保多租户查询不扫全表。

**应用不直接接入流量**：应用层无 `domain` / `access_mode` 字段。外部流量必须通过子站点的 `site_key` 鉴权，无法用 `app_key` 直接访问网关。

### 2.3 站点层职责边界（边界层能力）

站点层是**流量接入边界与运行时配置单元**，对应「一个可独立访问的域名」。其核心能力：

| 能力 | 实现方式 | 业务意义 |
|------|---------|---------|
| **流量身份** | `site_key`（格式 `site_<hex8>`）| 作为 `X-App-Key` 请求头的值，网关据此解析 `site_id` + `site_secret` |
| **域名绑定** | `domain`（主域名，创建后不可改）+ `alt_domains`（备用域名列表）| 服务端适配器按域名匹配站点 |
| **接入模式** | `access_mode` ∈ `{adapter, sdk}` | `adapter` = Nginx/CF Worker/WordPress，HTML 前拦截；`sdk` = 纯浏览器，HTML 后二次校验 |
| **专属网关** | `gateway_url`（可选）| 留空用部署级默认网关；填值则本站点流量走独立网关实例（多区域部署） |
| **运行时配置** | `clock_stats_enabled` / `log_retention_days` / `sdk_version` | 站点级差异化：某些站点关闭频控统计、调整日志保留期、锁定 SDK 版本 |
| **站点级规则** | `biz_rule_site.site_id` 关联表 | 规则与站点多对多，支持「同一条规则绑定多个站点」与「一个站点绑定多条规则」 |

**域名即边界**：客户端请求的 `Host` 头匹配 `domain` 或 `alt_domains` 任一项，即确定该请求属于本站点。ClickHouse `decision_events.host` 字段用于复盘域名分布与备用域名流量占比。

**SDK 的 `appId` 语义**：客户端 SDK 配置的 `appId` 实际是**站点主键** `site.id`（数字），而非应用主键。这是历史命名遗留，`app_id_design.md` 已明确说明映射关系。

### 2.4 跨层交互规则

#### 2.4.1 创建依赖

```
创建应用 (POST /v2/applications) → 得到 app_id
    ↓
创建站点 (POST /v2/sites, body 含 app_id) → 得到 site_id + site_key
    ↓
站点接入 (adapters 配置 site_key)
```

**强约束**：删除应用时，若名下仍有站点，返回 400 并提示先删站点（`applications.py:150` 前置检查）。外键 `biz_site.app_id → biz_application.id ON DELETE CASCADE` 是数据库层最后防线。

#### 2.4.2 密钥分层

| 层级 | 密钥字段 | 长度 | 生成方式 | 用途 |
|------|---------|------|---------|------|
| 应用 | `app_secret` | 128 | `secrets.token_urlsafe(96)` | HMAC 验签主密钥，轮换用 `POST /v2/applications/{app_id}/rotate-secret` |
| 站点 | `site_secret` | 128 | 同上，默认空串 | 可选增强，站点级签名独立轮换而不影响同应用其他站点 |

**验签顺序**：gateway `app_key.py:verify_request_signature()` 优先用 `site_secret`（非空时），回退 `app_secret`。这使得站点可选择性启用独立密钥，同时保留应用级统一密钥的便利性。

#### 2.4.3 规则继承与绑定

```sql
-- 应用级规则（app_id 非空，inherit_from_app=True）
SELECT * FROM biz_rule WHERE app_id = :app_id AND inherit_from_app = TRUE;
-- 自动对该应用下所有站点生效，网关按 site_id 加载时会把应用级规则一并拉入

-- 站点级规则（通过关联表绑定）
SELECT r.* FROM biz_rule r
JOIN biz_rule_site rs ON r.id = rs.rule_id
WHERE rs.site_id = :site_id;
```

**冲突处理**：优先级高的规则先命中即终止，应用级与站点级规则在同一优先级队列中按 `priority` 与 `id` 排序，无「应用级一定先于站点级」的隐式规则。运营需通过 `priority` 字段（critical / high / normal / low）显式控制优先级。

#### 2.4.4 数据隔离维度

| 层面 | 隔离键 | 实现方式 |
|------|--------|---------|
| 决策缓存 | `site_id` | Redis 键 `fangyu:decide:v2:{site_id}:{fingerprint}:{ip_hash}` |
| 频控计数 | `site_id` | ZSet 键 `fangyu:clock:rate:{site_id}:{dimension}:{value}` |
| 画像聚合 | `site_id` | `fangyu:profile:device:{site_id}:{fingerprint}` + `ip:{site_id}:{ip_hash}` |
| 访问日志 | `site_id` | ClickHouse `WHERE site_id = ?` 前缀过滤（注：列名实际为 `app_id`，值是站点主键） |
| 规则分片 | `site_id` | Redis Hash `fangyu:rules:site:{site_id}`，每站点一份完整规则副本 |

**跨站点查询权限**：`analytics.read` 与 `audit.read` 可按 `site_id=None` 查询应用下全部站点或全局，但接口层必须基于调用方权限决定是否放行，存储层不做强制隔离（便于平台级运营分析）。

### 2.5 核心业务流程（决策管线）

决策管线由 **11 个阶段**串联，按固定顺序执行。部分阶段命中后短路返回，部分阶段不短路只构建上下文。以下为完整流程：

```
[1] whitelist         短路 → allow()
[2] challenge_pass    短路 → allow()（凭据 TTL 内免挑战）
[3] clock             短路 → not_found()（频控超限/封禁）
[4] hybrid_lookup     条件短路（SDK 双层模式，服务端已判 hostile 时直接拦截）
[5] cache             短路 → 缓存内容（命中率目标 ≥85%）
[6] profile           不短路，构建 ProfileSnapshot
[7] decision_rule     短路 → 规则配置的处置（优先级最高的阶段）
[8] threat_intel      短路 → deny()（IP 黑名单）
[9] security          短路 → checker 返回的处置（Tor/VPN+数据中心等硬判定）
[10] risk_scoring     条件短路（score ≥ block_threshold 则拦截）
[11] default          兜底 → app_default 或 allow()
```

**关键设计约束**：

- **阶段 3（clock）必须前置于阶段 5（cache）**：频控依赖每个请求都被计数，放缓存后突发流量会漏计，频控失效。
- **阶段 1（whitelist）必须最前**：被频控封禁的访客加进白名单后仍然进不来，因为没走到 whitelist 阶段就被 clock 拦了。
- **频控结论不可缓存**：`DecisionOutcome.is_cacheable = not decided_by.is_time_sensitive`，四个时间敏感值为 `WHITELIST` / `CHALLENGE_PASS` / `CLOCK_BAN` / `CLOCK_RATE_LIMIT`。
- **缓存键不含 URL**：`(site_id, fingerprint, ip)` 三元组。跳转目标的占位符渲染发生在缓存读取**之后**，避免同一访客访问不同页面时复用第一次的跳转地址。

**短路阶段的 shadow 语义**：前 5 个阶段短路时**不传 shadow**，因为规则匹配尚未发生。影子规则影响面报表读作「进入规则匹配的流量里的占比」而非全站占比。

### 2.6 处置三层结构（正交模型）

V1 将「严重级别 × 执行机制」压成一维枚举（`ALLOW` / `CHALLENGE_CAPTCHA` / `BLOCK_HARD`...），每新增一种执行手段引发组合爆炸。V2 拆为三个独立维度：

| 维度 | 可选值 | 业务语义 |
|------|--------|---------|
| **Verdict（裁决）** | `trusted` / `suspect` / `hostile` | 为什么：风险判断，不涉及执行手段 |
| **Mechanism（机制）** | `pass` / `serve_alt` / `redirect` / `challenge` / `deny` / `not_found` | 怎么做：执行方式 |
| **TargetKind（目标）** | `origin` / `url` / `url_pool` / `page_resource` / `status_only` | 去哪：目标地址或资源 |

**合法组合矩阵**（`_MECHANISM_TARGET_KINDS`）：

- `pass` → `origin`
- `serve_alt` → `page_resource`（目标是资源名，非 URL）
- `redirect` → `url` / `url_pool`
- `challenge` → `origin`
- `deny` / `not_found` → `origin` / `status_only`

**正交性的价值体现**：`observe()` 工厂函数产出 `verdict=suspect` + `mechanism=pass` 的组合，即「放行但缩短缓存 TTL」，用于仅观测不干预的灰度场景。这在一维枚举模型中无法表达。

**地址池轮询策略**（`RotationStrategy`，5 种）：

| 策略 | 适用场景 | 是否有状态 | 注意事项 |
|------|---------|-----------|---------|
| `hash` | 默认，流量大时收敛均匀 | 无状态（blake2b 取模） | 短时可能倾斜 |
| `weighted` | 灰度放量、主备分流 | 无状态 | 权重归一化后摊数轴 |
| `sticky` | A/B 实验 | 无状态（seed=fingerprint） | 牺牲分摊性，池子退化为按访客分片 |
| `round_robin` | 严格轮转 | Redis 计数器 | 决策链路多一次写操作 |
| `failover` | 主备容灾 | 健康检查 + 配额 | 全部不健康时仍返回候选序列 |

**降级链路**：`redirect` 渲染失败（占位符非法 / 池内全部地址耗尽配额）时，mechanism 降级为 `pass`，httpStatus 必须按降级后机制重算（`resolve_http_status(mechanism, target)`），否则会下发 `mechanism=pass` 却 `httpStatus=302` 的矛盾值。

---

## 3. 技术架构设计

### 3.1 总体技术栈

| 层 | 技术选型 | 版本约束 | 选型理由 |
|---|---------|---------|---------|
| **Python 运行时** | CPython | `>=3.11` | 3.11 的 asyncio 性能提升 20-30%，Exception Groups 简化异常聚合 |
| **ASGI 服务器** | uvicorn + gunicorn | uvicorn `>=0.27`, gunicorn `>=21.2` | uvicorn 单进程异步，gunicorn 多进程管理 |
| **Web 框架** | FastAPI | `>=0.109,<1` | 原生 async/await、自动 OpenAPI、依赖注入、Pydantic v2 集成 |
| **ORM** | SQLAlchemy 2.0 + aiomysql | sqlalchemy `>=2.0`, aiomysql `>=0.2` | 异步 ORM、Mapped 类型安全、与 MySQL 8.4 `caching_sha2_password` 兼容 |
| **MySQL** | MySQL | `8.4` | V3 迁移强依赖 8.4 移除 `mysql_native_password`，aiomysql 需 cryptography `>=42.0` 做 RSA 握手 |
| **Redis** | Redis + hiredis | redis `>=5.0,<6`, hiredis 编译扩展 | 单线程高性能、Lua 脚本原子性、Stream 消息队列 |
| **ClickHouse** | ClickHouse Server | `24.8`（生产）/ `24.3`（测试）/ `23.8`（本地） | 列存、分区裁剪、物化视图聚合 |
| **前端框架** | Vue 3 + Vite | Vue `^3.5.21`, Vite `^7.1.5` | Composition API、script setup、Vite HMR |
| **UI 组件库** | Element Plus | `^2.11.2` | Vue 3 生态首选 |
| **前端状态** | Pinia | `^3.0.3` | Vue 3 官方推荐，替代 Vuex |
| **图表** | ECharts | `^6.0.0` | 访问日志时序、威胁分布、规则命中率 |
| **客户端 SDK** | TypeScript + Vite 库模式 | TS `5.6.3`, vitest `3.2.4` | UMD + ESM 双产物、零运行时依赖 |

**版本约束分层策略**：

- `shared` 包对所有依赖加上限（如 `pydantic>=2.6,<3`），收口版本范围
- `gateway-api` / `admin-api` 只声明下限，实际解析时由 shared 上限约束
- `client-sdk` 全部精确锁定（无 caret），确保产物字节级可复现

### 3.2 服务拓扑与模块依赖

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│ dashboard-ui │────────>│  admin-api   │────────>│    MySQL     │
│  (Vue 3)     │  Axios  │  (FastAPI)   │  async  │   (关系库)    │
└──────────────┘         └──────────────┘         └──────────────┘
                                │                          │
                                │ Redis                    │ Alembic
                                ↓                          │ migrations
                         ┌──────────────┐                 ↓
                         │    Redis     │         ┌──────────────┐
    ┌───────────┐        │ (配置/缓存)   │<────────│  ClickHouse  │
    │  adapters │        └──────────────┘         │  (分析库)     │
    │ (4 种)     │               ↑                └──────────────┘
    └───────────┘               │                        ↑
          │                     │                        │
          │ X-App-Key           │ Redis                  │ Stream
          ↓                     │ Read                   │ (事件)
    ┌──────────────┐     ┌──────────────┐               │
    │ gateway-api  │────>│    shared    │               │
    │  (决策引擎)   │     │  (契约包)     │               │
    └──────────────┘     └──────────────┘               │
          │                     ↑                        │
          │ /v2/decide          │                        │
          ↓                     │                        │
    ┌──────────────┐            │                        │
    │  client-sdk  │────────────┘                        │
    │  (浏览器)     │                                     │
    └──────────────┘                                     │
                                                         │
    ┌──────────────┐                                     │
    │    worker    │─────────────────────────────────────┘
    │  (ETL 消费)   │     asyncio                (当前缺失)
    └──────────────┘
```

**模块依赖层次**（从下到上）：

1. `shared`：跨服务契约包，零外部依赖。提供 schemas（decision / disposition / rule / event / profile / clock / whitelist）、operators（21 个规则操作符）、utils（crypto / clickhouse_manager / cache）。
2. `gateway-api`：依赖 shared、Redis、ClickHouse（只读）、MMDB。不依赖 MySQL。
3. `admin-api`：依赖 shared、MySQL、Redis、ClickHouse。持有 Alembic 迁移脚本。
4. `worker`：依赖 shared、Redis（消费 Stream）、ClickHouse（批写）。**当前源码缺失，仅测试存在**。
5. `dashboard-ui`：HTTP 调用 admin-api，无直接数据库连接。
6. `client-sdk`：仅依赖 Web API（Crypto / Fetch / Storage），零 npm 运行时依赖。
7. `adapters`：Nginx Lua / CF Worker / WordPress PHP / 通用嵌入 JS，各自独立，共享签名算法（四语言逐字节一致）。

### 3.3 部署拓扑

系统采用容器化部署，三套环境（本地开发 / 测试 / 生产）通过独立的 compose 文件与 `.env` 管理，K8s 清单作为生产可选形态。

#### 3.3.1 容器与端口映射

| 组件 | 容器内端口 | 本地开发 | 生产（宿主机绑定） | 测试环境 |
|------|-----------|---------|------------------|---------|
| gateway-api | 8080 | 8000 | `127.0.0.1:${GATEWAY_PUBLISH_PORT:-8000}` | 偏移端口 |
| admin-api | 8081 | 8081 | `127.0.0.1:${ADMIN_PUBLISH_PORT:-8081}` | 偏移端口 |
| worker | 9091（health）/ 9092（metrics） | 同容器端口 | 仅内网 | — |
| dashboard-ui | 80 | 8080 | 由前置 Nginx 反代 | — |
| MySQL | 3306 | 3306 | 仅内网 | 33306 |
| Redis | 6379 | 6379 | 仅内网 | 36379 |
| ClickHouse | 8123 / 9000 | 同容器端口 | 仅内网 | 38123 / 39000 |

生产环境所有数据存储端口**不对外暴露**，仅通过 Docker 内部网络 `fangyu-net`（bridge，子网 `${DOCKER_SUBNET:-172.28.0.0/16}`）访问；应用端口绑定 `127.0.0.1`，由宿主机 Nginx 统一终结 TLS 与限流。

#### 3.3.2 中间件版本约束

| 中间件 | 本地开发 | 测试 | 生产 | 收敛要求 |
|--------|---------|------|------|---------|
| MySQL | `8` | `8` | `8.4` | 统一至 `8.4`（见第 8 章 TD-M1） |
| Redis | `7-alpine` | `7.4-alpine` | `7.4-alpine` | 统一至 `7.4-alpine` |
| ClickHouse | `23.8` | `24.3-alpine` | `24.8` | 统一至 `24.8` |

**约束**：镜像 tag 必须固定到次版本，禁止使用 `latest`；跨环境版本漂移会导致 SQL 方言与物化视图行为差异，属于必须收敛的技术债。

#### 3.3.3 镜像构建约束

- 统一 `# syntax=docker/dockerfile:1.6`，启用 BuildKit 缓存挂载
- 多阶段构建：builder 阶段 `pip install --prefix=/install ./shared ./<service>`（**必须在同一条命令内安装**，否则 `fangyu_shared` 解析失败）
- 运行阶段以非 root 用户 `fangyu`（uid/gid 1000）启动
- `ENTRYPOINT` 统一使用 `tini`，保证信号透传与僵尸进程回收
- 前端镜像 builder 阶段执行 `pnpm build`，运行阶段仅保留 Nginx + 静态产物

#### 3.3.4 前置流量入口

宿主机 Nginx / OpenResty 承担四项职责：TLS 终结、限流、静态资源分发、反向代理。限流区划分：

| 限流区 | 速率 | 作用范围 |
|--------|------|---------|
| `gw_decide` | 100 r/s | `/v2/decide*` 决策热路径 |
| `gw_general` | 200 r/s | 其余网关端点 |

OpenResty 场景下 `defense.lua` 作为服务端 adapter 第一层，在 HTML 返回前完成拦截判定。

### 3.4 资源配置要求

#### 3.4.1 应用进程与容器资源

| 服务 | 进程模型 | CPU limit | 内存 limit | 说明 |
|------|---------|-----------|-----------|------|
| gateway-api | `GATEWAY_WORKERS`（生产建议 = CPU 核数） | 2 core | 1 GiB | 无状态，横向扩展主力 |
| admin-api | `ADMIN_WORKERS`（建议 2） | 1 core | 768 MiB | 低 QPS，写多读少 |
| worker | 单进程消费者组 | 1 core | 512 MiB | 可按 Stream 分片扩副本 |
| dashboard-ui | Nginx 静态 | 0.5 core | 256 MiB | 纯静态分发 |

#### 3.4.2 数据存储资源

| 组件 | 关键参数 | 建议值 | 依据 |
|------|---------|-------|------|
| MySQL | `innodb_buffer_pool_size` | ≥ 内存 50% | 18 张表体量小，热点集中在配置读取 |
| MySQL 连接池 | `pool_size` / `max_overflow` | 10 / 20（每进程） | 需保证 `workers × (pool+overflow) < max_connections` |
| Redis | `maxmemory` + `maxmemory-policy` | 2 GiB + `allkeys-lru` | 决策缓存与画像可淘汰；安全配置类键永不过期需单独评估 |
| ClickHouse | 磁盘 | 按 90 天 `decision_events` 保留期估算 | 主表 TTL 90 天、trace 7 天、DLQ 30 天 |

**约束**：Redis 采用 `allkeys-lru` 时，永不过期的安全配置类键存在被淘汰风险，须通过独立 DB 编号或前缀白名单隔离（见第 8 章）。

#### 3.4.3 可观测性配置

| 维度 | 实现 | 端点 / 配置 |
|------|------|-----------|
| 指标 | Prometheus 抓取 | gateway/admin `/metrics`，worker `:9092` |
| 健康检查 | HTTP 探针 | gateway/admin `/health`，worker `:9091` |
| 链路追踪 | OTLP → Jaeger | 由 `OTEL_EXPORTER_OTLP_ENDPOINT` 控制，未配置时自动关闭 |
| 决策 trace | ClickHouse `decision_traces` | 7 天保留，按需采样，用于回溯单次决策的 11 阶段执行路径 |
| 日志 | 结构化 JSON + traceId | 统一 `logging.getLogger(__name__)`，禁止 `print` |

---

## 4. 数据架构设计

### 4.1 存储选型与职责划分

| 存储 | 定位 | 承载数据 | 一致性要求 |
|------|------|---------|-----------|
| MySQL 8.4 | 权威配置源（System of Record） | 应用/站点、RBAC、规则、情报、系统配置，共 18 张业务表 | 强一致，事务保证 |
| Redis 7.4 | 决策热路径读取面 + 会话/频控状态 | 决策缓存、规则分片、画像、频控 ZSet、挑战凭据、nonce | 最终一致，可重建 |
| ClickHouse 24.8 | 分析型事件仓 | 决策事件、决策 trace、DLQ 与 9 个物化视图聚合 | 最终一致，允许重复（ReplacingMergeTree 去重） |

设计原则：**MySQL 写、Redis 读、ClickHouse 分析**。决策热路径**不直接读 MySQL**，所有配置由控制面写入 MySQL 后同步至 Redis 读取面；Redis 数据全部可从 MySQL 重建，故障时允许 fail-open 降级。

### 4.2 核心业务数据模型

#### 4.2.1 App-Site 双层主干

```
biz_application (应用/业务分组)
  id, app_key, app_secret, name, status, default_disposition, created_at, updated_at
        │ 1:N  ON DELETE CASCADE
        ▼
biz_site (站点/流量接入边界)
  id, app_id, site_key, site_secret, domain, access_mode, status, created_at, updated_at
```

| 字段 | 所属层 | 用途 |
|------|-------|------|
| `app_key` / `app_secret` | 应用层 | 控制面身份与业务分组标识 |
| `site_key` / `site_secret` | 站点层 | 数据面 HMAC 验签凭据（`X-App-Key` 实际携带 site_key） |
| `domain` | 站点层 | 流量归属判定 |
| `access_mode` | 站点层 | 接入模式（服务端 adapter / SDK / hybrid 双层） |
| `default_disposition` | 应用层 | 决策管线 `default` 阶段的兜底处置 |

**约束**：删除应用级联删除其下全部站点及依赖数据；`site_id = 0` 为全局哨兵值，表示规则/配置作用于应用下所有站点。

#### 4.2.2 表分组

| 分组 | 表数 | 代表表 | 职责 |
|------|-----|--------|------|
| App/Site 双层 | 2 | `biz_application`、`biz_site` | 业务主干 |
| RBAC | 7 | 用户、角色、权限、用户角色、角色权限、会话、审计日志 | 控制面权限与追溯 |
| 规则 | 4 | 规则、规则组、规则-站点绑定、规则条件 | 决策规则配置 |
| 情报与安全 | 6 | IP 黑白名单、ASN、威胁情报源、频控限制、页面资源 | 决策依据数据 |
| 系统配置 | 3 | 系统配置、字典、通知配置 | 全局参数 |

**已知列名漂移**（见第 8 章）：`biz_clock_limits`、`biz_page_resource` 数据库实际列名为 `app_id`，ORM 模型声明为 `site_id`；`RuleModel` 未映射 V3 新增的 `app_id` / `inherit_from_app`。

### 4.3 数据流转路径

#### 4.3.1 决策链路（数据面，写后异步）

```
访客请求
  → adapter / SDK 采集上下文（六通道指纹 + 请求特征）
  → POST /v2/decide（HMAC-SHA256 验签）
  → 11 阶段决策管线（仅读 Redis，不读 MySQL）
  → 返回三层处置（verdict × mechanism × target_kind）
  → XADD fangyu:events:decision（Redis Stream，非阻塞）
  → worker 消费者组批量拉取
  → 批量 INSERT ClickHouse decision_events
  → 9 个物化视图实时聚合
  → 失败重试超限 → decision_events_dlq（30 天）
```

**关键约束**：事件投递不得阻塞决策响应；Stream 写入失败仅记日志，不影响处置结果（`[HA-*]` fail-open 原则）。

#### 4.3.2 配置链路（控制面，写后同步）

```
Dashboard 操作
  → admin-api（JWT + RBAC 权限校验）
  → 事务写 MySQL（权威源）
  → 写审计日志
  → 同步刷新 Redis 读取面（规则分片 / 名单 / 频控配置）
  → gateway 下次决策即生效（无需重启）
```

#### 4.3.3 Hybrid 双层闭环

```
第一层：服务端 adapter 在 HTML 返回前调用 /v2/decide → 下发一次性 serverToken
第二层：client-sdk 采集真实指纹 → 携带 serverToken 调 /v2/sdk/* 二次校验
        → hybrid_lookup 阶段读取第一层结论；若已判 hostile 直接短路拦截
```

### 4.4 Redis 键空间与 TTL 策略

| 键模板 | 类型 | TTL | 用途 |
|--------|------|-----|------|
| `fangyu:decide:v2:{site_id}:{fingerprint}:{ip_hash}` | String | 短（决策缓存窗口） | 决策结果缓存，目标命中率 ≥85% |
| `fangyu:rules:site:{site_id}` | Hash | 永不过期 | 规则分片读取面 |
| `fangyu:profile:device:{site_id}:{fingerprint}` | Hash | 3600s | 设备画像聚合 |
| `fangyu:clock:rate:{site_id}:{dimension}:{value}` | ZSet | 3900s | 频控滑动窗口计数 |
| `fangyu:behavior:{site_id}:{fingerprint}` | Hash | 1800s | 行为特征累积 |
| `fangyu:challenge:pass:{...}` | String | 300s | 挑战通过凭据（免重复挑战） |
| `fangyu:nonce:{...}` | String | 300s | 验签防重放，一次性消费 |
| `fangyu:hybrid:token:{serverToken}` | String | 300s | 双层接入一次性令牌 |
| `fangyu:events:decision` | Stream | — | 决策事件投递队列 |

TTL 分三档：

1. **永不过期**：安全配置类（规则分片、名单），由控制面主动刷新
2. **短 TTL 300s**：防重放与会话类（nonce、挑战凭据、serverToken）
3. **中等 TTL**：聚合类（画像 3600s、频控 3900s、行为 1800s）

**[HA-001] 约束**：除安全配置类外，所有 key 必须显式设置过期时间。

### 4.5 ClickHouse 事件模型

| 表 | 引擎 | TTL | 排序键 |
|----|------|-----|-------|
| `decision_events` | ReplacingMergeTree | 90 天 | `(app_id, occurred_at, event_id)` |
| `decision_traces` | MergeTree | 7 天 | 按决策 ID |
| `decision_events_dlq` | MergeTree | 30 天 | 按投递时间 |
| 9 个物化视图 | SummingMergeTree | 跟随主表 | 按聚合维度 |

物化视图覆盖：按站点/时间的处置分布、风险分数分布、命中阶段分布、Top IP / Top 指纹、频控触发统计等，支撑 Dashboard 秒级查询，避免对主表全表扫描。

**已知问题**：DDL 列名为 `app_id`，而 `access_log_query.py` / `analytics_query.py` 查询使用 `site_id`，属未完成的重命名重构（见第 8 章 TD-B4）。

### 4.6 数据安全与权限管控

#### 4.6.1 多租户隔离

所有查询必须携带归属过滤，遵循 `[SEC-002]`：

| 层面 | 隔离键 | 实现 |
|------|-------|------|
| 决策缓存 | `site_id` | key 前缀内嵌 |
| 频控计数 | `site_id` | key 前缀内嵌 |
| 画像聚合 | `site_id` | key 前缀内嵌 |
| 访问日志 | `site_id` | ClickHouse `WHERE` 条件 |
| 规则分片 | `site_id` | Redis Hash 分片 |
| MySQL 配置 | `app_id` + `site_id` | ORM `filter()` 强制携带 |

#### 4.6.2 敏感数据处理

| 数据 | 处理方式 |
|------|---------|
| 访客 IP | 存储前哈希 `sha256_hex(ip)[:32]`，原始 IP 不落盘 |
| `site_secret` / `app_secret` | 仅创建时明文返回一次，库中加密存储 |
| 用户密码 | bcrypt 哈希 |
| 日志中的密钥/token | `***` 脱敏（`[LOG-001]`） |
| `.env` 真实配置 | 必须 `.gitignore` + `chmod 600`（`[SH-003]`） |

#### 4.6.3 RBAC 权限模型

23 个权限码 × 4 个系统角色：

| 角色码 | 权限范围 |
|--------|---------|
| `super_admin` | `*`（全通配） |
| `admin` | 除系统级配置外全部读写 |
| `operator` | 规则/名单/站点的读写，无用户管理权 |
| `auditor` | 全局只读 + 审计日志查看 |

权限匹配支持三级通配：精确码（`rule.write`）→ 资源通配（`rule.*`）→ 全通配（`*`）。

**已知问题**：`applications.py` 使用冒号分隔符 `app:read`，其余文件使用点号 `app.read`，需统一（见第 8 章）。

---

## 5. 接口设计规范

### 5.1 统一响应格式

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": { },
  "request_id": "01J..."
}
```

错误响应（遵循 `[ERR-001]`）：

```json
{
  "code": "ERR_RULE_NOT_FOUND",
  "message": "规则不存在",
  "details": { "rule_id": 123 },
  "request_id": "01J..."
}
```

**约束**：`request_id` 全链路贯穿（`[LOG-002]`），必须在所有响应与日志中携带；数据面 `/v2/decide` 为性能考虑直接返回处置体，不套 `data` 包装。

### 5.2 错误码体系

| 前缀 | 分类 | HTTP 状态 |
|------|------|----------|
| `ERR_AUTH_*` | 认证失败（无凭据、签名错、时间戳超窗、nonce 重放） | 401 |
| `ERR_PERM_*` | 权限不足（RBAC 校验失败） | 403 |
| `ERR_NOT_FOUND_*` | 资源不存在 | 404 |
| `ERR_VALIDATION_*` | 入参校验失败（Pydantic） | 422 |
| `ERR_CONFLICT_*` | 唯一约束冲突（重复 site_key / domain） | 409 |
| `ERR_RATE_LIMIT` | 限流触发 | 429 |
| `ERR_DEPENDENCY_*` | 下游依赖故障（MySQL / Redis / ClickHouse） | 503 |
| `ERR_INTERNAL` | 未预期内部错误 | 500 |

**约束**：禁止空 `except`（`[ERR-002]`），ORM/驱动异常必须转换为上述业务错误码；异常堆栈仅进日志，不返回客户端。

**已知问题**：限流 429 响应当前返回 `{"error": ...}`，缺 `code` / `message` / `details` / `request_id`，不符统一格式（见第 8 章）。

### 5.3 数据面接口（gateway-api）

| 端点 | 方法 | 用途 | 认证 |
|------|------|------|------|
| `/v2/decide` | POST | 完整决策，执行 11 阶段管线 | `X-App-Key` + HMAC 签名 |
| `/v2/decide/fast` | POST | 轻量决策，跳过高开销阶段 | 同上 |
| `/v2/challenge/verify` | POST | 挑战答案校验，通过后写 300s 免挑战凭据 | 同上 |
| `/v2/sdk/collect` | POST | SDK 上报六通道指纹与行为特征 | 同上 + serverToken |
| `/v2/sdk/verify` | POST | 双层接入第二层校验 | 同上 + serverToken |
| `/health` | GET | 存活与依赖探针 | 无 |
| `/metrics` | GET | Prometheus 指标 | 内网限制 |

#### 5.3.1 请求契约要点（`/v2/decide`）

请求体为 `DecisionContext`，核心字段分组：

| 分组 | 字段 | 说明 |
|------|------|------|
| 归属 | `site_key` | 站点标识，服务端解析为 `site_id` / `app_id` |
| 请求特征 | `ip`、`user_agent`、`url`、`referer`、`method`、`headers` | `request.*` 规则命名空间数据源（snake_case） |
| 指纹 | `fingerprint`、六通道原始值 | 投票产出稳定指纹，缺失通道自愈 |
| 设备 | `device.*` | 屏幕、时区、语言、硬件并发（camelCase） |
| 行为 | 鼠标轨迹、停留时长、交互次数 | `interaction` / `behavior` scorer 输入 |
| 双层 | `serverToken` | hybrid 模式必填，一次性消费 |

#### 5.3.2 响应契约要点

响应体为三层正交处置：

| 字段 | 取值 | 说明 |
|------|------|------|
| `verdict` | `trusted` / `suspect` / `hostile` | 结论层，用于统计与告警 |
| `mechanism` | `pass` / `serve_alt` / `redirect` / `challenge` / `deny` / `not_found` | 执行手段 |
| `target_kind` | `origin` / `url` / `url_pool` / `status_only` / `page_resource` | 目标类型，须与 mechanism 组合合法 |
| `target` | 具体目标值 | `url_pool` 时按轮询策略选取 |
| `score` | 0–100 | 风险分，`min(100, max(0, Σ(sᵢ·wᵢ)))` |
| `stage` | 命中阶段名 | 11 阶段之一，用于归因 |
| `decision_id` | ULID | 关联 ClickHouse trace |

**约束**：`mechanism × target_kind` 组合必须通过 `_MECHANISM_TARGET_KINDS` 矩阵校验，非法组合在契约层直接拒绝，禁止运行期兜底。

### 5.4 认证与验签规范

数据面采用 HMAC-SHA256 签名，三步校验：

1. **凭据解析**：`X-App-Key` 头携带 `site_key`，服务端查 Redis 读取面获取 `site_secret`
2. **签名比对**：请求参数按键字典序排序 → 各值 URL 编码 → 拼接 `k=v&k=v` → HMAC-SHA256(secret) → 与 `X-Signature` 常量时间比对
3. **防重放**：`X-Timestamp` 与服务端时间偏差须在 ±300s 内（双向容忍）；`X-Nonce` 写入 Redis 并设 300s TTL，重复即拒

**四语言一致性约束**：TypeScript（client-sdk）/ Python（gateway）/ Lua（OpenResty adapter）/ PHP（WordPress adapter）四端签名实现必须逐字节一致，由 `sign_vectors.json` 测试向量锁定，任一端修改必须同步更新全部实现并通过向量校验。

**开关约束**：`GATEWAY_SIGNATURE_REQUIRED` 生产环境必须为 `true`。当前三处默认值不一致（`.env.example`=`true` / `.env.production.example`=`false` / prod compose 插值默认=`true`），须收敛为统一 `true`（见第 8 章）。

### 5.5 控制面接口（admin-api）

按资源域划分，共 24 个路由模块，全部要求 JWT 认证 + RBAC 权限码校验：

| 资源域 | 路径前缀 | 权限码 |
|--------|---------|-------|
| 认证 | `/v2/auth` | 无（登录/刷新/登出） |
| 应用 | `/v2/applications` | `app.read` / `app.write` |
| 站点 | `/v2/sites` | `site.read` / `site.write` |
| 规则 | `/v2/rules`、`/v2/rule-groups` | `rule.read` / `rule.write` |
| 名单与情报 | `/v2/ip-lists`、`/v2/asn`、`/v2/threat-intel` | `intel.read` / `intel.write` |
| 频控 | `/v2/clock-limits` | `clock.read` / `clock.write` |
| 页面资源 | `/v2/page-resources` | `resource.read` / `resource.write` |
| 分析 | `/v2/analytics`、`/v2/access-logs` | `analytics.read` |
| 用户与角色 | `/v2/users`、`/v2/roles`、`/v2/permissions` | `user.*` / `role.*` |
| 审计 | `/v2/audit-logs` | `audit.read` |
| 系统 | `/v2/system`、`/v2/diagnostics` | `system.read` / `system.write` |

**归属校验要求**：所有站点级资源的写操作（PUT / DELETE）必须校验目标资源归属当前租户的 `app_id` / `site_id`。当前 `page_resources.py` 的全局 PUT / DELETE 缺失归属校验，存在跨站点越权风险（阻断级，见第 8 章）。

**路由冲突**：`apps.py` 与 `sites.py` 均注册 `/sites` 前缀，`sites_router` 先注册导致 `apps.py` 11 个端点中 9 个为死代码，须删除或改前缀（见第 8 章）。

### 5.6 限流规约

| 对象 | 阈值 | 维度 | 实现层 |
|------|------|------|-------|
| 决策接口 | 100 req/min | 站点 | 应用层（Redis ZSet） |
| 决策热路径 | 100 r/s | IP | Nginx `gw_decide` |
| 网关通用 | 200 r/s | IP | Nginx `gw_general` |
| 登录接口 | 5 req/min | IP + 账号 | 应用层 |
| 业务频控 | 站点自定义 | IP / 指纹 / 自定义维度 | `clock` 阶段 |

**约束**：应用层限流与 Nginx 限流双层生效，前者按业务维度、后者按连接维度；应用层限流不可依赖内存计数（多 worker 场景失效），必须走 Redis。

---

## 6. 非功能需求设计

### 6.1 性能指标

| 指标 | 目标值 | 测量点 | 达成手段 |
|------|-------|-------|---------|
| 决策 P95 时延 | < 50 ms | `/v2/decide` 服务端处理 | Redis 单跳读取面 + 缓存命中 + 异步事件投递 |
| 决策 P99 时延 | < 120 ms | 同上 | 阶段级超时 + fail-open |
| 吞吐量 | ≥ 10000 QPS | 网关集群 | 无状态横向扩展 + `GATEWAY_WORKERS` 多进程 |
| 缓存命中率 | ≥ 85% | `cache` 阶段 | 三元组 key（site_id + fingerprint + ip_hash） |
| 事件投递延迟 | < 5 s | XADD → ClickHouse 可查 | worker 批量消费 |
| 单元测试覆盖率 | ≥ 80% 整体 | CI | 分层差异化要求（见 6.4） |

**热路径硬约束**：
- 决策链路禁止访问 MySQL
- 决策链路禁止同步 HTTP 外呼（威胁情报走预加载 + 异步刷新）
- 事件投递必须非阻塞，失败不影响响应

### 6.2 可用性设计

#### 6.2.1 SLA 目标

| 服务 | 可用性目标 | 降级形态 |
|------|-----------|---------|
| gateway-api（数据面） | 99.95% | fail-open 放行 |
| admin-api（控制面） | 99.5% | 只读或不可用，不影响数据面 |
| worker（事件） | 99% | 积压在 Stream，恢复后追平 |
| Dashboard | 99% | 静态资源可 CDN 兜底 |

**核心原则**：控制面故障**不得影响**数据面决策。数据面只依赖 Redis 读取面，MySQL 与 admin-api 完全宕机时决策仍可正常执行。

#### 6.2.2 降级策略（fail-open 清单）

| 故障点 | 降级行为 | 影响 |
|--------|---------|------|
| Redis 不可用 | 跳过 cache / clock / profile 阶段，走 `default` 兜底 | 防护能力下降，业务不中断 |
| 威胁情报数据缺失 | `threat_intel` 阶段跳过 | 少一层判定依据 |
| ClickHouse 不可用 | worker 重试，超限进 DLQ | 分析数据延迟，决策无影响 |
| Redis Stream 写失败 | 记 warn 日志，返回处置 | 该次事件丢失统计 |
| 规则解析异常 | 该规则跳过，继续后续阶段 | 单规则失效，不阻断管线 |

**约束**：所有降级路径必须打点（Prometheus counter），禁止静默降级。

#### 6.2.3 容灾方案

| 层面 | 方案 |
|------|------|
| 应用层 | 无状态多副本，任一实例故障由 Nginx 健康检查摘除 |
| MySQL | 主从 + 每日全量备份 + binlog 增量，RPO ≤ 5 min |
| Redis | AOF everysec + 主从；数据全部可从 MySQL 重建，RTO 以重建耗时为界 |
| ClickHouse | 单副本 + 分区级备份；DLQ 保留 30 天支持重放补数 |
| 配置 | `.env` 与 K8s Secret 离线加密备份，密钥支持轮换 |

### 6.3 可扩展性设计

#### 6.3.1 横向扩展

- **gateway-api**：完全无状态（所有状态在 Redis），直接增加副本
- **worker**：Redis Stream 消费者组天然支持多消费者，增副本即分摊
- **admin-api**：无状态，但写操作集中，扩展收益有限
- **Redis**：热点在 decide 缓存，可按 `site_id` 哈希分片
- **ClickHouse**：按 `app_id` 与时间分区，可扩分布式表

#### 6.3.2 纵向扩展点（插件化契约）

| 扩展点 | 新增方式 | 约束 |
|--------|---------|------|
| 风险评分器（Scorer） | 实现 Scorer 接口并注册权重 | 输出 0–100，权重需重新校准阈值 |
| 决策阶段（Stage） | 在管线注册新阶段 | 明确是否短路，必须补 trace 打点 |
| 处置机制（Mechanism） | 扩展枚举 + 更新组合矩阵 | 须同步四端 adapter 实现 |
| 规则操作符 | 扩展操作符表 | 须定义数据缺失时的行为 |
| 轮询策略 | 实现 RotationStrategy | 有状态策略需 Redis 支撑 |
| 接入适配器 | 新增 adapter | 必须通过 `sign_vectors.json` 签名向量 |

### 6.4 质量与工程约束

| 分层 | 单函数行数上限 | 覆盖率要求 |
|------|--------------|-----------|
| domain | ≤ 30 行 | ≥ 95% |
| application | ≤ 50 行 | ≥ 85% |
| infrastructure | ≤ 50 行 | ≥ 75% |
| interfaces | ≤ 30 行 | ≥ 70% |

强制门禁（须全部接入 CI）：

- 后端：`ruff` + `mypy --strict` + `pytest --cov`（`fail_under=80` 需实际带 `--cov` 才生效）
- 前端：`tsc --noEmit` + `eslint` + `vitest run`
- SDK：`vitest run` + `tsc --noEmit` + 签名向量校验
- 迁移：Alembic 迁移必须可 upgrade / downgrade 往返

**当前缺口**：client-sdk 的 `vitest run` 与 `tsc --noEmit` 未接入 CI；`mypy --strict` 无 CI 入口；coverage 门禁未实际生效（见第 8 章）。

### 6.5 安全合规要求

| 项 | 要求 |
|----|------|
| 传输安全 | 全链路 HTTPS，TLS 1.2+，由前置 Nginx 终结 |
| 接口防伪 | HMAC-SHA256 强制开启，生产禁止关闭 |
| 防重放 | 时间戳 ±300s + nonce 一次性消费 |
| 越权防护 | 所有写操作强制归属校验（`[SEC-002]`） |
| 入参校验 | Pydantic 全量类型/范围/非空校验（`[SEC-001]`） |
| SQL 注入 | 全部走 ORM 构建器，禁止字符串拼接（`[ORM-001]`） |
| 密钥管理 | 仅从 `.env` 读取，禁止硬编码（`[DIR-001]`）；支持轮换 |
| 日志脱敏 | 密码/token/secret 一律 `***`（`[LOG-001]`） |
| 隐私合规 | 访客 IP 哈希化存储；指纹为技术标识符，不含 PII |
| 审计追溯 | 控制面全部写操作落审计日志，含操作人、IP、前后值 |
| 数据保留 | 事件 90 天、trace 7 天、DLQ 30 天，到期自动清理 |

**违规项**：V3 迁移 `20260808_0002_app_site_clean_rebuild.py` 硬编码 `'change_me_in_production'`，违反 `[DIR-001]`；`defense.lua` 残留 `[fangyu-test]` 调试日志，违反 `[FLOW-002]`。二者必须在上线前清除。

---

## 7. 项目实施规划

### 7.1 迭代阶段划分

实施以「先恢复可运行、再补齐一致性、最后做性能与体验」为主线，分四个阶段。

#### 阶段一：可运行性修复（P0，阻断级）

| 交付项 | 内容 |
|--------|------|
| worker 服务落地 | 补齐 `worker/` 源码，使现有 8 个测试文件可运行，打通 Stream → ClickHouse |
| admin-api 可启动 | 修复 `apps.py` / `diagnostics.py` 的依赖注入导入错误 |
| gateway 验签可用 | 修正 `app_key.py` 中 `credential.app_secret` / `app_id` 字段名 |
| SDK 端点可用 | 修正 `sdk.py` 中 `_resolve_app_id` → `_resolve_site_id` |
| 越权修复 | `page_resources.py` 全局 PUT / DELETE 补归属校验 |

**里程碑 M1**：三服务全部可启动，`/v2/decide` 端到端可通，事件可落 ClickHouse。

#### 阶段二：命名与契约一致性收敛（P1）

| 交付项 | 内容 |
|--------|------|
| app/site 命名统一 | 收敛 ORM 模型、迁移、ClickHouse 查询三处的 `app_id` / `site_id` 漂移 |
| 路由冲突消除 | 处理 `apps.py` 与 `sites.py` 的 `/sites` 前缀冲突 |
| 权限码统一 | 冒号分隔符统一为点号 |
| 响应格式统一 | 限流 429 补齐 `code` / `message` / `details` / `request_id` |
| 配置收敛 | `GATEWAY_SIGNATURE_REQUIRED` 三处统一；清除迁移硬编码密钥 |
| 环境对齐 | 三套环境中间件版本统一；K8s 清单与 compose/.env 对齐 |
| 文档更新 | 重写已过期的 `API_CONTRACTS.md` |

**里程碑 M2**：命名与契约全链路一致，`API_CONTRACTS.md` 与代码零偏差。

#### 阶段三：质量门禁与可观测性补齐（P1）

| 交付项 | 内容 |
|--------|------|
| CI 门禁 | 接入 client-sdk 测试与类型检查、`mypy --strict`、生效 coverage 门禁 |
| 覆盖率提升 | 整体 ≥80%，domain ≥95% |
| 打点补齐 | 11 阶段全量 trace；SECURITY 阶段补传 score |
| 调试代码清理 | 清除 `defense.lua` 及全项目调试日志 |
| 文档同步 | `decision_service.py` docstring 补齐 11 阶段 |

**里程碑 M3**：CI 全绿且门禁生效，可观测性覆盖全部决策阶段与降级路径。

#### 阶段四：性能压测与上线（P2）

| 交付项 | 内容 |
|--------|------|
| 压测 | 验证 P95 < 50ms、QPS ≥ 10000、缓存命中率 ≥ 85% |
| 容灾演练 | Redis / MySQL / ClickHouse 单点故障下的降级验证 |
| 密钥轮换演练 | `site_secret` 轮换过程零中断验证 |
| 灰度上线 | 单站点 → 单应用 → 全量 |

**里程碑 M4**：性能达标、容灾可控，具备生产上线条件。

### 7.2 风险应对预案

| 风险 | 影响 | 应对 |
|------|------|------|
| worker 补齐工作量超预期 | M1 延期 | 复用 tests/worker 已有逻辑，优先实现最小可用版本 |
| ClickHouse 列名漂移影响范围大 | M2 延期 | 先统一迁移 DDL，再批量修改查询，保持向后兼容中间态 |
| 覆盖率从当前值提升至 80% 耗时长 | M3 延期 | 按分层差异化要求逐层收敛，不阻断 M1/M2 |
| 压测未达性能目标 | M4 阻断 | 按瓶颈分类：缓存未命中 → 分析 key 设计；序列化慢 → 换 msgpack；数据库慢 → 索引与连接池 |
| 生产环境依赖配置与本地不一致 | 上线故障 | 用 `docker-compose config` 预验证；分阶段灰度，每阶段验证健康检查与降级 |

---

## 8. 已知技术债与收敛计划

本章列出代码调研中发现的全部已知缺陷，按阻断级（P0）→ 高（P1）→ 中（P2）→ 低（P3）分级。

### 8.1 阻断级（P0）—— 必须在上线前修复

| 编号 | 问题 | 影响 | 收敛方案 |
|------|------|------|---------|
| **TD-A1** | `worker/` 源码目录整体缺失 | Stream 有生产者无消费者，ClickHouse 写入链路断开 | 参考 `tests/worker/` 8 文件 1158 行实现，补齐 worker 服务；阶段一交付 |
| **TD-A2** | admin-api 无法启动 | `apps.py:13-14`、`diagnostics.py:27` 导入不存在的 `get_app_service` / `get_app_repo`，`v2/__init__.py` 无条件 import 触发 ImportError | 改为 `get_application_service` / 导入删除 / 懒加载；阶段一交付 |
| **TD-A3** | gateway 验签必然崩溃 | `app_key.py` 8 处访问 `credential.app_secret` / `app_id`，实际字段 `site_secret` / `site_id`；`signature_required` 默认 `True`，全部 decide 请求 AttributeError | 修正字段名；阶段一交付 |
| **TD-A4** | `sdk.py` 三端点 NameError | 5 处调用 `_resolve_app_id`（实际函数名 `_resolve_site_id`） | 改为正确函数名；阶段一交付 |
| **TD-A5** | `app_key.py:145` NameError | 使用未定义的 `site_id`（参数名 `app_id`） | 修正变量名；阶段一交付 |
| **TD-A6** | `page_resources.py` 越权漏洞 | 221/244 行全局 PUT / DELETE 无归属校验，可跨站点修改删除 | 查询前补 `filter(site_id=当前租户)`；阶段一交付 |

### 8.2 高优先级（P1）—— 影响一致性与合规

| 编号 | 问题 | 影响 | 收敛方案 |
|------|------|------|---------|
| **TD-B1** | ORM 模型列名漂移 | `biz_clock_limits`、`biz_page_resource` 库为 `app_id`，模型声明 `site_id`；`RuleSiteModel` / `RuleGroupModel` 外键指向 `biz_application.id`，V3 建的是 `biz_site.id`；`RuleModel` 未映射 V3 新增的 `app_id` / `inherit_from_app` | 对齐模型与库，补 Alembic 迁移修正外键；阶段二交付 |
| **TD-B2** | V3 迁移硬编码密钥 | `20260808_0002_app_site_clean_rebuild.py:209` INSERT `'change_me_in_production'`，违反 `[DIR-001]` | 改为从环境变量读取或不插 seed 数据；阶段二交付 |
| **TD-B3** | `GATEWAY_SIGNATURE_REQUIRED` 三处不一致 | `.env.example`=`true`、`.env.production.example`=`false`、prod compose 插值默认=`true` | 统一为 `true`；阶段二交付 |
| **TD-B4** | ClickHouse 列名冲突 | DDL 为 `app_id`，`access_log_query.py` / `analytics_query.py` 查询写 `site_id`；且 `access_log_query.py` 15 处未定义变量（`app_clause` / `site_clause`、`app_id` / `site_id` 混用） | 统一为 `app_id`（保持 DDL）或 `site_id`（改 DDL + 数据迁移）；阶段二交付 |
| **TD-B5** | `apps.py` 与 `sites.py` 路由冲突 | 同为 `/sites`，`sites_router` 先注册，`apps.py` 11 个端点中 9 个为死代码 | 删除 `apps.py` 死代码或改前缀为 `/applications/{id}/sites`；阶段二交付 |
| **TD-B6** | 权限码分隔符不一致 | `applications.py` 用 `app:read`/`app:write`，其余用 `app.read`/`app.write` | 统一为点号；阶段二交付 |
| **TD-B7** | 限流 429 响应不符统一格式 | 返回 `{"error": ...}`，缺 `code` / `message` / `details` / `request_id` | 改为 `SuccessResponse` 结构；阶段二交付 |
| **TD-B8** | K8s 清单与 compose/.env 漂移 | Stream 名（`fangyu:decision:events` vs `fangyu:events:decision`）、库名（`fangyu_admin` vs `fangyu_v2`）、worker 端口（9100 vs 9091/9092）、JWT TTL（1800 vs 604800） | 以 compose/.env 为准同步 K8s；阶段二交付 |
| **TD-B9** | 中间件版本三套不齐 | ClickHouse 23.8 / 24.8 / 24.3-alpine；Redis `7-alpine` / `7.4-alpine`；MySQL `8` / `8.4` | 统一至生产版本（MySQL 8.4、Redis 7.4-alpine、ClickHouse 24.8）；阶段二交付 |
| **TD-B10** | CI 覆盖缺口 | client-sdk 的 `vitest run` 与 `tsc --noEmit` 未接入 CI；mypy strict 无 CI 入口；coverage `fail_under=80` 因未带 `--cov` 不生效 | 补齐 CI 流水线三项；阶段三交付 |
| **TD-B11** | `defense.lua` 调试日志残留 | 多处 `ngx.log(ngx.ERR, "[fangyu-test]...")`，违反 `[FLOW-002]` | 全部删除或改为 `ngx.DEBUG` + 生产关闭；阶段三交付 |

### 8.3 中优先级（P2）—— 影响可维护性

| 编号 | 问题 | 影响 | 收敛方案 |
|------|------|------|---------|
| **TD-C1** | `decision_service.py` 文档过时 | 模块 docstring 只列 9 阶段，缺 `challenge_pass` / `hybrid_lookup` | 补齐至 11 阶段；阶段三交付 |
| **TD-C2** | SECURITY 阶段不传 score | `_finalize` 未传 score，命中时 `outcome.score` 恒为 0.0，而 THREAT_INTEL / CLOCK 给 100.0 | 传入当前累积 score；阶段三交付 |
| **TD-C3** | `API_CONTRACTS.md` 已过期 | 203 行草案与代码大面积不符 | 完整重写或删除；阶段二交付 |
| **TD-C4** | Redis 永不过期键存在被淘汰风险 | `maxmemory-policy` 为 `allkeys-lru`，安全配置类键永不设 TTL，可能被淘汰 | 方案一：独立 DB 编号隔离；方案二：改为 `volatile-lru` + 所有键显式 TTL；阶段四交付 |

### 8.4 低优先级（P3）—— 不影响功能

| 编号 | 问题 | 影响 | 收敛方案 |
|------|------|------|---------|
| **TD-D1** | 规范文档技术栈描述错误 | `project-rule.md` 写 Tortoise-ORM，实际用 SQLAlchemy 2.0 | 更新文档；随迭代进行 |
| **TD-D2** | 测试覆盖率未达标 | 当前整体未实测，目标 ≥80%、domain ≥95% | 按分层差异化补齐；阶段三持续进行 |

### 8.5 收敛里程碑映射

- **M1（阶段一）**：修复 TD-A1 ~ A6 全部阻断级
- **M2（阶段二）**：修复 TD-B1 ~ B9 + C3
- **M3（阶段三）**：修复 TD-B10 ~ B11 + C1 ~ C2 + D2
- **M4（阶段四）**：修复 TD-C4，验证所有修复项

**验证方式**：每项修复附单元测试或端到端用例，回归套件通过方视为收敛完成。

---

## 附录 A：术语与缩略语

| 术语 | 说明 |
|------|------|
| App-Site 双层架构 | `biz_application`（应用/业务分组）→ `biz_site`（站点/流量边界），1:N 关系 |
| DDD | Domain-Driven Design，领域驱动设计 |
| HMAC | Hash-based Message Authentication Code，哈希消息认证码 |
| RBAC | Role-Based Access Control，基于角色的访问控制 |
| ORM | Object-Relational Mapping，对象关系映射 |
| TTL | Time To Live，生存时间 |
| QPS | Queries Per Second，每秒查询数 |
| P95 / P99 | 第 95 / 99 百分位延迟 |
| SLA | Service Level Agreement，服务等级协议 |
| RPO / RTO | Recovery Point / Time Objective，恢复点/时间目标 |
| DLQ | Dead Letter Queue，死信队列 |
| ULID | Universally Unique Lexicographically Sortable Identifier |
| Evercookie | 跨多通道持久化访客标识技术 |
| Verdict | 结论层（trusted / suspect / hostile） |
| Mechanism | 执行手段（pass / serve_alt / redirect / challenge / deny / not_found） |
| Target Kind | 目标类型（origin / url / url_pool / page_resource / status_only） |
| Scorer | 风险评分器，输出 0–100 单维度分数 |
| Stage | 决策管线阶段（11 个） |
| fail-open | 故障时放行，保业务可用性优先于防护能力 |

---

## 附录 B：参考文档

| 文档路径 | 说明 |
|---------|------|
| `docs/architecture/LAYERED_ARCHITECTURE.md` | DDD 四层架构规范 |
| `docs/migration-app-site-separation.md` | App-Site 双层架构迁移方案 |
| `docs/app-id-design.md` | 双 ID 设计说明 |
| `docs/modules/RULE_CONDITIONS.md` | 规则条件与操作符完整清单 |
| `infrastructure/clickhouse/init.sql` | ClickHouse 表与物化视图 DDL |
| `shared/src/fangyu_shared/schemas/disposition.py` | 三层正交处置契约 |
| `.trae/rules/project-rule.md` | 项目编码规范 |
| `README.md` | 项目结构与核心原则 |

---

**文档结束**
