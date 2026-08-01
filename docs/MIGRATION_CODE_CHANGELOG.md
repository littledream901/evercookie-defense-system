# V1 → V2 代码变更清单

## 新增服务

| 服务 | 位置 | 职责 |
| --- | --- | --- |
| shared | `shared/src/fangyu_shared/` | 通用 schema、异常、日志、缓存客户端、工具 |
| gateway-api | `gateway-api/` | 决策 API、五级流水线、Stream 生产者 |
| admin-api | `admin-api/` | 管理台后端，RBAC、规则版本、分析查询 |
| worker | `worker/` | Redis Stream 消费者，批量落 ClickHouse |
| dashboard-ui | `dashboard-ui/` | 管理台前端（Vite + Vue3 + Naive UI） |

## 目录级别改动

- 舍弃 `code-project/backend`（V1）。
- 保留 `code-project/frontend` 作为参考实现，V2 前端在 `Evercookie Defense System V2/dashboard-ui/`。
- 舍弃 Tortoise ORM，全面切换 SQLAlchemy 2.0 async。
- 引入 Alembic：`admin-api/alembic/`。

## Shared 包（8 个子包）

- `fangyu_shared.schemas.*`：Pydantic v2 契约（decision / rule / audit / analytics / auth）
- `fangyu_shared.exceptions.*`：`BusinessException` 基类 + 8 个业务异常
- `fangyu_shared.logging.*`：结构化日志上下文
- `fangyu_shared.cache.*`：Redis 客户端 + 序列化
- `fangyu_shared.clickhouse.*`：aiochclient 封装
- `fangyu_shared.utils.*`：字符串脱敏、时间、id
- `fangyu_shared.observability.*`：Prometheus 指标
- `fangyu_shared.streams.*`：Redis Stream 生产/消费封装

## gateway-api 关键模块

- `domain/decision/pipeline.py`：五级流水线
- `domain/decision/disposition.py`：处置解析
- `application/decision_service.py`：编排
- `infrastructure/redis/rule_source.py`：读 Redis Hash 规则
- `infrastructure/streams/log_producer.py`：写 Redis Stream
- `interfaces/http/decisions.py`：POST `/v2/decisions`

## admin-api 关键模块

- `domain/rbac/{entities,policy}.py`：RBAC 领域模型
- `domain/rule/{entity,state_machine,version}.py`：规则领域
- `application/services/{auth,user,role,rule,app}_service.py`：应用层服务
- `infrastructure/repositories/*_repository.py`：SQLAlchemy 仓储
- `infrastructure/cache/{permission,rule}_cache.py`：两级缓存
- `infrastructure/clickhouse/analytics_query.py`：分析查询
- `interfaces/http/v2/*`：完整 v2 路由（auth/users/roles/permissions/apps/rules/analytics/health）
- `interfaces/http/dependencies.py`：DI + JWT + require_permission
- `alembic/versions/*`：初始 schema + seed

## worker 关键模块

- `application/consumer.py`：XREADGROUP 循环
- `application/batch_writer.py`：批量 flush ClickHouse
- `infrastructure/deadletter.py`：DLQ 处理

## dashboard-ui

- `src/api/*.js`：8 大模块 API 封装（auth/users/roles/permissions/apps/rules/analytics）
- `src/utils/http.js`：双 Token 拦截器，401 自动 refresh
- `src/store/{app,user}.js`：Pinia stores
- `src/router/{index,routes}.js`：权限守卫 + `require_permission` 路由 meta
- `src/layout/`：侧栏 + 顶栏 + 主内容
- `src/views/{login,dashboard,users,roles,permissions,apps,rules,analytics,profile}/`：9 个业务页面

## 基础设施

- `infrastructure/docker/{gateway,admin,worker,dashboard}.Dockerfile`
- `infrastructure/kubernetes/`：Namespace/ConfigMap/Secret/Deployment/Service/HPA/Ingress/NetworkPolicy/PDB + kustomization
- `infrastructure/nginx/{dashboard,gateway}.conf`
- `infrastructure/monitoring/{prometheus.yml,alertmanager.yml,rules/*.rules.yml}`

## 测试

- `tests/shared/`：shared 包纯 Python 单测（strings、exceptions）
- `tests/admin/`：admin-api 领域测试（RBAC policy、规则状态机）
- `tests/gateway/`：gateway-api 领域测试（disposition 解析）
- `Makefile`：`test-shared / test-admin / test-gateway` 分服务运行
- `tests/README.md`：测试指南（含集成/性能/安全测试规划）

## 破坏性变更（相对 V1）

1. 认证接口路径从 `/api/auth/*` 迁到 `/v2/auth/*`。
2. Token 从单一 access 变成 access + refresh，登录响应结构变化。
3. RBAC 权限码采用 `resource.action`，V1 的自定义标签不兼容。
4. 规则条件从 SQL DSL 改为结构化 JSON（`[{field, op, value}]`）。
5. 分析接口全部改为 POST + JSON body（原为 GET query）。
6. 数据库表名前缀统一：`sys_*` / `biz_*`；V1 表将被弃用（迁移脚本详见部署手册）。
