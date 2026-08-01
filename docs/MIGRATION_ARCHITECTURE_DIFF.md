# V1 → V2 架构差异对比

## 1. 目标差异

| 维度 | V1 | V2 |
| --- | --- | --- |
| 部署形态 | 单体 API 服务（`code-project/backend`）+ 独立 dashboard-ui | 三服务拆分：gateway-api + admin-api + worker，共享 shared 包 |
| 分层 | 传统 MVC（router/service/model） | DDD 四层：domain / application / infrastructure / interfaces |
| ORM | Tortoise ORM + Aerich | SQLAlchemy 2.0 async + Alembic |
| 认证 | 单一 access token | Access + Refresh 双 Token，客户端自动刷新 |
| 决策路径 | 请求 → service 内联判断 → 落库 | Gateway 五级流水线：识别 → 特征 → 规则 → 决策 → 处置 |
| 数据链路 | 直写 MySQL | Gateway → Redis Stream → worker → ClickHouse（决策日志）+ MySQL（配置） |
| 缓存 | 无 | 两级：请求内 dict + Redis（权限缓存、规则缓存） |
| 分析 | MySQL 聚合 | ClickHouse 按时序聚合，参数化查询 |
| 前端 | Naive UI + Pinia + Axios | 保留 Naive UI + Pinia + Axios，重构菜单/API 契约对齐 v2 |
| 部署 | Docker Compose | Kubernetes：ConfigMap / Secret / HPA / PDB / NetworkPolicy |
| 观测 | 无正式指标 | Prometheus + Alertmanager，指标 recording rule + 服务级告警 |

## 2. 三服务边界

```
┌───────────┐   POST /decisions           ┌────────────┐
│  接入方   │ ──────────────────────────→ │ gateway-api│
└───────────┘                             │ (决策 API) │
                                          └──────┬─────┘
                                                 │  XADD stream
                                                 ▼
                                          ┌────────────┐
                                          │  Redis     │
                                          │  Stream    │
                                          └──────┬─────┘
                                                 │ XREADGROUP
                                                 ▼
                                          ┌────────────┐
                                          │  worker    │
                                          │ (批量落 CH)│
                                          └──────┬─────┘
                                                 ▼
                                          ┌────────────┐
                                          │ ClickHouse │
                                          └────────────┘

┌───────────┐   /v2/*                     ┌────────────┐
│ dashboard │ ──────────────────────────→ │ admin-api  │
└───────────┘                             │ (管理台)   │
                                          └──────┬─────┘
                                                 │ 同步规则到 Redis Hash
                                                 ▼
                                                Redis  ← gateway 读规则
```

## 3. 数据模型差异

- **V1** 用户、角色、权限混杂在若干张 `auth_*` 表，用户直接绑定权限字符串。
- **V2** 严格 RBAC：`sys_user` ↔ `sys_user_role` ↔ `sys_role` ↔ `sys_role_permission` ↔ `sys_permission`，权限使用 `resource.action` 编码 + `*` 通配。
- **V2** 应用/规则位于 `biz_*` 前缀，规则新增 `biz_rule_version` 存历史快照支持回滚。

## 4. 权限模型

V1 无正式 RBAC，写死角色。V2 用 `PermissionPolicy` + `PermissionContext`，逻辑集中在 `admin-api/src/domain/rbac`，路由层通过 `require_permission("resource.action")` 声明。

## 5. 规则发布流水线

V1 直写规则表 → gateway 读表。V2 状态机严格：`draft → published / disabled → archived`，每次改动生成 `RuleVersion` 快照，发布/回滚都同步 Redis Hash `fangyu:rules:{app_id}`，gateway 只读 Redis。

## 6. 部署链路

- 构建：`infrastructure/docker/{gateway,admin,worker,dashboard}.Dockerfile` 多阶段镜像。
- 编排：`infrastructure/kubernetes/*.yaml` + kustomization。
- 边缘：Nginx（`dashboard.conf` / `gateway.conf`）承担静态 + SPA fallback + 反代 + 边缘限流。
- 观测：`infrastructure/monitoring/{prometheus,alertmanager,rules/*}`。
