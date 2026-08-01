# V2 部署操作手册

面向生产上线的完整步骤。假设操作节点已配置 `kubectl`、`docker`、`python 3.11+`、`pnpm`、`git`。

## 0. 环境需求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.11+ | 后端三服务 |
| Node | 20+ | 前端构建 |
| pnpm | 9.x | 前端包管理 |
| MySQL | 8.0+ | 元数据（用户、角色、规则等） |
| Redis | 7.x | 缓存 + Stream |
| ClickHouse | 24.x | 决策日志时序库 |
| Kubernetes | 1.27+ | 编排 |
| Prometheus | 2.50+ | 观测 |
| Alertmanager | 0.27+ | 告警 |

## 1. 拉取代码

```bash
git clone <repo>
cd "evercookie-defense-system/Evercookie Defense System V2"
```

## 2. 数据库初始化

### 2.1 建库

```sql
CREATE DATABASE fangyu DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'fangyu'@'%' IDENTIFIED BY '<STRONG_PASSWORD>';
GRANT ALL PRIVILEGES ON fangyu.* TO 'fangyu'@'%';
FLUSH PRIVILEGES;
```

### 2.2 迁移

```bash
cd admin-api
python -m pip install -e .
export ADMIN_DATABASE_URL='mysql+aiomysql://fangyu:<STRONG_PASSWORD>@<HOST>:3306/fangyu'
alembic upgrade head          # 建表 + 灌基础数据
```

### 2.3 修改默认管理员密码

seed 里 `admin / Admin@fangyu2026`，**必须立刻通过 dashboard 或 API 修改**：

```bash
curl -X POST http://<admin-api>/v2/auth/change-password \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"old_password":"Admin@fangyu2026","new_password":"<新密码>"}'
```

## 3. 配置

- `admin-api`：环境变量或 `.env`（参考 `docs/deployment/ENVIRONMENT_SETUP.md`）
  - `DATABASE_URL`、`REDIS_URL`、`CLICKHOUSE_URL`、`JWT_SECRET`、`JWT_ALGORITHM`、`ACCESS_TOKEN_TTL`、`REFRESH_TOKEN_TTL`
- `gateway-api`：`REDIS_URL`、`STREAM_KEY`、`RULE_CACHE_TTL`
- `worker`：`REDIS_URL`、`CLICKHOUSE_URL`、`BATCH_SIZE`、`FLUSH_INTERVAL`
- 前端 `dashboard-ui/.env`：`VITE_API_BASE=/api`、`VITE_API_TARGET=<admin-api>`

## 4. 构建镜像

```bash
docker build -f infrastructure/docker/gateway.Dockerfile -t fangyu/gateway-api:v2.0.0 .
docker build -f infrastructure/docker/admin.Dockerfile -t fangyu/admin-api:v2.0.0 .
docker build -f infrastructure/docker/worker.Dockerfile -t fangyu/worker:v2.0.0 .
docker build -f infrastructure/docker/dashboard.Dockerfile -t fangyu/dashboard-ui:v2.0.0 .
docker push ...
```

## 5. K8s 部署

```bash
cd infrastructure/kubernetes
kubectl apply -k .
kubectl -n fangyu rollout status deploy/gateway-api
kubectl -n fangyu rollout status deploy/admin-api
kubectl -n fangyu rollout status deploy/worker
kubectl -n fangyu rollout status deploy/dashboard-ui
```

### 5.1 探针

- Liveness：`/healthz`（不检查外部依赖）
- Readiness：`/readyz`（依赖 Redis + MySQL + ClickHouse，degraded 时返回 503）

### 5.2 HPA

- gateway-api：CPU 60% / mem 70%
- worker：Stream 积压指标（PromQL）

## 6. Nginx 边缘

- `infrastructure/nginx/dashboard.conf`：静态资源 + SPA fallback + 反代 `/api → admin-api`
- `infrastructure/nginx/gateway.conf`：反代 `/decisions`，含边缘限流

## 7. 观测

```bash
kubectl -n monitoring apply -f infrastructure/monitoring/prometheus.yml
kubectl -n monitoring apply -f infrastructure/monitoring/rules/
kubectl -n monitoring apply -f infrastructure/monitoring/alertmanager.yml
```

关键指标：
- `fangyu_gateway_requests_total`
- `fangyu_gateway_decision_latency_seconds`
- `fangyu_worker_stream_lag`
- `fangyu_admin_5xx_ratio`

## 8. 冒烟测试

```bash
# 决策接口
curl -X POST http://<gateway>/v2/decisions \
  -H "X-App-Key: <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"request_id":"t1","subject":{"ip":"1.1.1.1"}}'

# 管理台
curl -X POST http://<admin>/v2/auth/login -d '{"username":"admin","password":"..."}'
```

## 9. 上线检查清单

- [ ] Alembic `alembic current` 已到最新
- [ ] admin/gateway/worker 三服务 Pod Ready
- [ ] `/readyz` 全部返回 200
- [ ] Prometheus 目标全绿
- [ ] Alertmanager 无 firing
- [ ] 默认 admin 密码已修改
- [ ] 默认应用的 API Key 已发放并本地保存
- [ ] Nginx TLS 证书有效期 ≥ 30 天

## 10. 回滚

```bash
# 应用回滚
kubectl -n fangyu rollout undo deploy/admin-api
kubectl -n fangyu rollout undo deploy/gateway-api

# 数据库回滚（仅在必要时）
cd admin-api
alembic downgrade -1
```

## 11. 备份

- MySQL：`mysqldump fangyu | gzip > fangyu-$(date +%F).sql.gz`
- ClickHouse：`clickhouse-backup create --tables fangyu.*`
- Redis：AOF + RDB 双开
