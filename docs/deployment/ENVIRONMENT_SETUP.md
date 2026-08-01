# V2 环境搭建与部署指南

**用途**: 本地开发、CI/CD、生产部署的一次性说明

---

## 一、本地开发环境

### 1.1 前置条件

| 工具 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.11 | 支持 `asyncio.TaskGroup` |
| Node.js | 20 LTS | 前端 + SDK 构建 |
| Docker | 24+ | 容器化开发 |
| Docker Compose | v2 | 编排 |
| Make | 任意 | 命令封装 |
| uv 或 poetry | latest | Python 依赖管理 |
| pnpm | 8+ | 前端包管理 |

### 1.2 一键启动

```bash
# 1. 克隆并进入 V2 目录
cd "e:\Python\evercookie-defense-system\Evercookie Defense System V2"

# 2. 复制环境变量
cp .env.example .env

# 3. 启动基础设施（Redis + MySQL + ClickHouse）
make infra-up

# 4. 安装 Python 依赖
make install-py

# 5. 安装前端依赖
make install-ui

# 6. 数据库迁移
make db-migrate

# 7. 启动全部服务（Gateway + Admin + Worker + UI）
make dev
```

### 1.3 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Gateway API | 8000 | 决策引擎 |
| Admin API | 8001 | 管理后台 API |
| Dashboard UI | 5173 | 前端（Vite dev server） |
| Worker | - | 后台进程 |
| Redis | 6379 | 缓存 + Stream |
| MySQL | 3306 | 配置存储 |
| ClickHouse | 8123, 9000 | 分析存储 |
| Prometheus | 9090 | 监控 |
| Grafana | 3000 | 可视化 |

---

## 二、docker-compose.yml 骨架

```yaml
version: '3.9'

services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["redis-data:/data"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s

  mysql:
    image: mysql:8
    ports: ["3306:3306"]
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: fangyu_v2
    volumes: ["mysql-data:/var/lib/mysql"]

  clickhouse:
    image: clickhouse/clickhouse-server:23
    ports: ["8123:8123", "9000:9000"]
    volumes: ["clickhouse-data:/var/lib/clickhouse"]
    ulimits:
      nofile: 262144

  gateway-api:
    build: ./gateway-api
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [redis, mysql, clickhouse]
    volumes: ["./gateway-api:/app"]

  admin-api:
    build: ./admin-api
    ports: ["8001:8001"]
    env_file: .env
    depends_on: [redis, mysql, clickhouse]
    volumes: ["./admin-api:/app"]

  worker:
    build: ./worker
    env_file: .env
    depends_on: [redis, clickhouse]
    volumes: ["./worker:/app"]

  dashboard-ui:
    build: ./dashboard-ui
    ports: ["5173:5173"]
    volumes: ["./dashboard-ui:/app", "/app/node_modules"]

  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes: ["./infrastructure/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml"]

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    volumes: ["grafana-data:/var/lib/grafana"]

volumes:
  redis-data:
  mysql-data:
  clickhouse-data:
  grafana-data:
```

---

## 三、Makefile 骨架

```makefile
.PHONY: help infra-up infra-down dev test lint build clean

help:
	@echo "常用命令:"
	@echo "  make infra-up      启动基础设施"
	@echo "  make dev           启动开发环境"
	@echo "  make test          运行全部测试"
	@echo "  make lint          代码检查"
	@echo "  make build         构建 Docker 镜像"

infra-up:
	docker compose up -d redis mysql clickhouse prometheus grafana

infra-down:
	docker compose down

install-py:
	cd shared && uv pip install -e .
	cd gateway-api && uv pip install -e .
	cd admin-api && uv pip install -e .
	cd worker && uv pip install -e .

install-ui:
	cd dashboard-ui && pnpm install
	cd client-sdk && pnpm install

db-migrate:
	cd admin-api && alembic upgrade head

dev:
	docker compose up -d

test:
	pytest --cov --cov-report=term-missing
	cd dashboard-ui && pnpm test
	cd client-sdk && pnpm test

lint:
	ruff check .
	ruff format --check .
	mypy --strict shared gateway-api/src admin-api/src worker/src
	bandit -r . -ll

build:
	docker compose -f docker-compose.prod.yml build

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
```

---

## 四、CI/CD 流水线

### 4.1 GitHub Actions（`.github/workflows/ci.yml`）

```yaml
name: CI

on:
  push: { branches: [main, develop] }
  pull_request: { branches: [main, develop] }

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install ruff mypy bandit
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy --strict shared gateway-api/src admin-api/src worker/src
      - run: bandit -r . -ll

  test-backend:
    runs-on: ubuntu-latest
    services:
      redis: { image: redis:7-alpine, ports: ['6379:6379'] }
      mysql:
        image: mysql:8
        env: { MYSQL_ROOT_PASSWORD: root, MYSQL_DATABASE: test }
        ports: ['3306:3306']
      clickhouse:
        image: clickhouse/clickhouse-server:23
        ports: ['8123:8123']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install uv && uv pip install -e ./shared -e ./gateway-api -e ./admin-api -e ./worker
      - run: pytest --cov --cov-fail-under=80

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - uses: pnpm/action-setup@v3
      - run: cd dashboard-ui && pnpm install && pnpm test
      - run: cd client-sdk && pnpm install && pnpm test

  build:
    runs-on: ubuntu-latest
    needs: [lint, test-backend, test-frontend]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          tags: fangyu/gateway-api:${{ github.sha }}
```

---

## 五、生产部署

### 5.1 Kubernetes（推荐）

```
infrastructure/kubernetes/
├── namespace.yaml
├── configmap.yaml
├── secrets.yaml
├── gateway-api/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── hpa.yaml           # HPA 自动扩缩容
├── admin-api/
├── worker/
│   └── deployment.yaml    # 2 副本足够
└── ingress.yaml
```

**关键配置**：
- Gateway API：3-10 副本，HPA 基于 CPU 70%
- Admin API：2 副本
- Worker：2 副本（避免消费重复）
- Redis Sentinel / Cluster
- MySQL 主从
- ClickHouse 集群（3 节点）

### 5.2 灰度发布流程

见 `docs/REWRITE_PLAN.md` § 6.4 灰度发布策略。

---

## 六、监控与告警

### 6.1 Prometheus 抓取配置

```yaml
# infrastructure/monitoring/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'gateway-api'
    static_configs:
      - targets: ['gateway-api:8000']
    metrics_path: /metrics

  - job_name: 'admin-api'
    static_configs:
      - targets: ['admin-api:8001']
    metrics_path: /metrics
```

### 6.2 Grafana 仪表盘

- **决策引擎**：QPS、P95 延迟、缓存命中率、规则命中 Top 10
- **数据管道**：Stream 长度、Worker 消费速率、DLQ 堆积
- **系统健康**：CPU/内存、连接数、错误率
- **业务大盘**：日活、拦截率、误判率

### 6.3 告警渠道

- Prometheus AlertManager → Slack / 钉钉 / 飞书
- 严重告警：值班电话（PagerDuty）

---

**文档结束**
