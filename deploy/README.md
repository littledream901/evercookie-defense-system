# 生产部署指南

Evercookie Defense System V2 在 1Panel + OpenResty + Docker 环境下的部署手册。

## 架构

```
公网
 │
 ├── admin.example.com   ──┐
 └── defense.example.com ──┤  1Panel OpenResty（持有 80/443，TLS 终结）
                           │
                    ┌──────┴──────┐
                    │  127.0.0.1  │
                    ├─ :8080 ─────┤ dashboard-ui 容器（内置 Nginx）
                    │             │   └─ /api/* → admin-api:8081
                    └─ :8000 ─────┘ gateway-api 容器

内部网络 fangyu-net（不对公网暴露）
  admin-api:8081   worker（无端口）
  mysql:3306   redis:6379   clickhouse:8123/9000
```

关键点：

- 80/443 归 1Panel OpenResty，容器只发布回环端口
- 数据层端口全部绑定 `127.0.0.1`，公网不可达
- 前端与 admin-api 同源，由 UI 容器内 Nginx 反代，避免跨域
- gateway-api 独立域名，SDK 跨站调用走应用层 CORS 白名单

## 目录

| 文件 | 用途 |
|---|---|
| `deploy.sh` | **统一入口**，所有部署与运维操作走这里 |
| `docker-compose.prod.yml` | 生产编排 |
| `openresty/admin.conf.template` | 后台站点配置模板 |
| `openresty/gateway.conf.template` | 网关站点配置模板 |
| `scripts/preflight.sh` | 部署前检查 |
| `scripts/gen-secrets.sh` | 生成随机凭据 |
| `scripts/rollback.sh` | 回滚 |
| `scripts/backup.sh` | 全量备份 |
| `scripts/smoke-test.sh` | 部署后冒烟测试 |
| `scripts/check-ssl.sh` | 证书校验 |

`scripts/` 下是各环节的具体实现，`deploy.sh` 负责编排调用。日常只需用 `deploy.sh`。

## 命令总览

```bash

cd /opt/fangyu-defense-system

bash deploy/deploy.sh help          # 完整用法

# 部署
bash deploy/deploy.sh clone <目录>  # 克隆代码并自动 init
bash deploy/deploy.sh init          # 首次部署
bash deploy/deploy.sh update        # 更新部署
bash deploy/deploy.sh rollback      # 回滚

# 运维
bash deploy/deploy.sh status        # 状态总览
bash deploy/deploy.sh logs [服务]   # 跟踪日志
bash deploy/deploy.sh restart       # 重启应用层
bash deploy/deploy.sh stop / start / down
bash deploy/deploy.sh shell [服务]  # 进容器

# 检查
bash deploy/deploy.sh preflight     # 部署前检查
bash deploy/deploy.sh verify        # 冒烟测试
bash deploy/deploy.sh doctor        # 故障诊断
bash deploy/deploy.sh ssl <域名>    # 证书校验
bash deploy/deploy.sh backup        # 全量备份
```

## 服务器要求

| 项 | 最低 | 建议 |
|---|---|---|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 50 GB | 100 GB+ |
| Docker | 24.0 | 最新稳定版 |
| 1Panel | 1.10 | 最新稳定版 |

内存低于 8 GB 时需下调 `MYSQL_BUFFER_POOL`、`REDIS_MAXMEMORY` 与各服务 worker 数。
ClickHouse 明细数据增长快，磁盘按 90 天保留期估算。

## 快速部署

```bash
export GIT_REPO=https://github.com/littledream901/evercookie-defense-system.git
bash deploy/deploy.sh clone /opt/fangyu-defense-system
```

`clone` 会拉代码后自动转入 `init`。`init` 依次完成：生成凭据 → 交互式配置域名 → 环境预检 → 拉基础镜像 → 构建业务镜像 → 启动数据层并等待健康 → 启动应用层 → 数据库迁移 → 端点验收。

任一环节失败会中止并打印日志尾部，完整日志留在 `deploy/.logs/`。

已有代码时直接 `cd /opt/fangyu && bash deploy/deploy.sh init`。

部署完成后仍需手工做两件事：在 1Panel OpenResty 配置反代站点、登录后台改默认口令。

## 手工部署步骤

需要逐步控制时按下面走。

### 1. 准备代码与配置

```bash
git clone <repo> /opt/fangyu && cd /opt/fangyu
git checkout main

cp .env.production.example .env.production
bash deploy/scripts/gen-secrets.sh    # 自动生成随机口令
chmod 600 .env.production
```

`gen-secrets.sh` 只填充口令类占位符，以下三项必须手工改：

```bash
ADMIN_CORS_ORIGINS=["https://admin.yourdomain.com"]
GATEWAY_CORS_ORIGINS=["https://www.yourdomain.com"]
IMAGE_TAG=v2.0.0
```

`*_CORS_ORIGINS` 是 pydantic 的 `list[str]`，**必须写 JSON 数组**。写成逗号分隔字符串会让服务启动时解析失败直接崩溃。

同时修改前端生产配置 `dashboard-ui/.env.production`：

```bash
VITE_GATEWAY_URL = https://defense.yourdomain.com
```

`VITE_API_URL` 保持 `/` 不要改——前端与 admin-api 同源，由 UI 容器内 Nginx 反代。

### 2. 预检

```bash
bash deploy/scripts/preflight.sh
```

必须做到阻塞项为 0。脚本会检查资源、端口冲突、占位符残留、CORS 格式、连接串主机名、compose 语法与前端 Mock 地址。

### 3. 部署

```bash
bash deploy/deploy.sh init
```

配置已就绪时 `init` 会跳过凭据生成与域名询问，直接进入预检与构建。

非交互环境（CI）加 `NON_INTERACTIVE=1` 跳过所有提示。

### 4. 配置 OpenResty 站点

1Panel → 网站 → 创建反向代理网站，域名分别填后台域名与网关域名，申请 Let's Encrypt 证书。

在站点配置文件中套用模板，替换占位符：

| 占位符 | 说明 |
|---|---|
| `{{ADMIN_DOMAIN}}` | 后台域名 |
| `{{GATEWAY_DOMAIN}}` | 网关域名，须与 `VITE_GATEWAY_URL` 一致 |
| `{{UI_PORT}}` | `UI_PUBLISH_PORT`，默认 8080 |
| `{{GATEWAY_PORT}}` | `GATEWAY_PUBLISH_PORT`，默认 8000 |
| `{{OFFICE_CIDR}}` | 允许访问后台的办公网段 |
| `{{INTERNAL_CIDR}}` | 允许抓 `/metrics` 的内网网段 |

应用后校验并重载：

```bash
docker exec 1Panel-openresty-* openresty -t
docker exec 1Panel-openresty-* openresty -s reload
```

### 5. 验证

```bash
bash deploy/deploy.sh ssl admin.yourdomain.com defense.yourdomain.com
ADMIN_USER=admin ADMIN_PASS='xxx' bash deploy/deploy.sh verify
```

首次部署后立即登录后台修改默认管理员口令。

## 升级部署

```bash
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=v2.0.1/' .env.production
bash deploy/deploy.sh update
```

`update` 会拉代码、备份、构建新镜像、执行迁移，再逐个替换应用层容器，数据层不动。

两个设计细节：

- **迁移在换容器之前执行**，用 `docker compose run --rm` 从新镜像起临时容器跑 `alembic upgrade head`。用 `exec` 会打到旧容器，里面是旧镜像的迁移脚本，本次新增的迁移根本不存在。这也要求迁移必须向后兼容——旧代码要能跑在新表结构上，否则迁移完到容器替换完这段时间会报错。
- **忘记改 `IMAGE_TAG` 时会提示**。同 tag 构建会覆盖旧镜像，回滚随之失效。禁止长期使用 `latest`。

## 回滚

```bash
bash deploy/deploy.sh rollback          # 回滚到上一版
bash deploy/deploy.sh rollback v2.0.0   # 回滚到指定版本
```

**回滚只处理镜像，不处理数据库。** 若本次发布包含破坏性迁移（删列、改类型、删表），必须先恢复数据库：

```bash
# 1. 停应用层，保留数据层
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production \
  stop gateway-api admin-api worker dashboard-ui

# 2. 恢复 MySQL
gunzip -c deploy/backups/<时间戳>/mysql_fangyu_v2.sql.gz \
  | docker exec -i fangyu-mysql sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" fangyu_v2'

# 3. 回滚镜像
bash deploy/deploy.sh rollback v2.0.0
```

评审迁移脚本时就要判断是否可逆。不可逆的迁移应拆成两次发布：先加新列双写，确认无误后再删旧列。

## 备份

```bash
bash deploy/deploy.sh backup
RETAIN_DAYS=30 bash deploy/scripts/backup.sh   # 自定义保留天数
```

建议在 1Panel 计划任务中每日执行。备份内容：

- MySQL 全量（`--single-transaction`，不锁表）
- ClickHouse 表结构与行数（明细表靠 TTL 与副本，不做全量导出）
- Redis RDB 快照（缓存数据，可从 MySQL/CH 重建）
- 镜像清单与 Git commit，用于定位回滚目标

备份不含 `.env.production` 本体（含明文口令），只记录键名。口令请单独存入密码管理器。

## 常见问题

**服务启动即退出，日志报 pydantic ValidationError**

`*_CORS_ORIGINS` 写成了逗号分隔字符串。改为 JSON 数组：`["https://a.com","https://b.com"]`。

**前端登录报网络错误，接口 404**

检查 `dashboard-ui/.env.production` 的 `VITE_API_URL` 是否为 `/`。前端请求 `/api/v2/*`，由 UI 容器内 Nginx 剥离 `/api` 前缀后转给 admin-api 的 `/v2/*`。

**决策日志页面为空，但网关有流量**

事件链路断在 Redis Stream。确认 `GATEWAY_EVENT_STREAM_NAME` 与 `WORKER_STREAM_NAME` 完全一致：

```bash
docker exec fangyu-redis sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
  XINFO GROUPS fangyu:events:decision'
```

**Analytics 页面报表查不到数据**

ClickHouse 库名必须是 `fangyu`。`analytics_query.py` 与 `reputation_sync_service.py` 中的表前缀是硬编码的，改库名会导致查不到表。

**MMDB 上传失败，提示权限拒绝**

`mmdb-data` 卷属主不是 uid 1000。镜像已预建目录处理此问题；若卷是旧版本遗留的，手工修正：

```bash
docker run --rm -v fangyu_mmdb-data:/data alpine chown -R 1000:1000 /data
```

**数据库连接超时**

连接串里写了 `localhost`。容器内 `localhost` 指向容器自身，必须用服务名 `mysql` / `redis` / `clickhouse`。

**口令含特殊字符导致连接失败**

连接串中的口令需 URL 编码：`@` → `%40`，`:` → `%3A`，`/` → `%2F`。`gen-secrets.sh` 生成的口令只含字母数字，不受此影响。

## 安全清单

部署后逐项确认：

- [ ] `.env.production` 权限 600，未提交到 Git
- [ ] 所有 `__REPLACE_*__` 占位符已替换
- [ ] `ADMIN_JWT_SECRET` 长度 ≥ 32 且非示例值
- [ ] `*_CORS_ORIGINS` 无通配 `*`
- [ ] MySQL / Redis / ClickHouse 端口仅绑定 `127.0.0.1`
- [ ] 后台域名已按办公网段收口，或已启用 VPN
- [ ] `/metrics` 仅内网可访问
- [ ] HTTPS 强制跳转与 HSTS 已生效
- [ ] TLS 仅保留 1.2 / 1.3
- [ ] `GATEWAY_APP_KEY_REQUIRED=true`
- [ ] 默认管理员口令已修改
- [ ] 每日备份计划任务已配置并验证过恢复流程

## 运维命令

```bash
cd /opt/fangyu

bash deploy/deploy.sh status              # 版本、容器、健康、资源、重启次数
bash deploy/deploy.sh logs admin-api 200  # 跟踪指定服务日志
bash deploy/deploy.sh restart gateway-api # 重启单个服务
bash deploy/deploy.sh shell admin-api     # 进容器
bash deploy/deploy.sh doctor              # 部署异常时的定向诊断
```

`doctor` 覆盖本项目最常踩的坑：退出容器的日志、CORS 是否为 JSON 数组、连接串是否误写 localhost、内部服务连通性、gateway 与 worker 的 Stream 名是否一致、ClickHouse 库名是否为 `fangyu`。

需要直接操作 compose 时：

```bash
cd /opt/fangyu/deploy
alias dc='docker compose -f docker-compose.prod.yml --env-file ../.env.production'

dc ps
dc exec admin-api alembic current
dc up -d --scale gateway-api=3    # 横向扩容，需同步改 OpenResty upstream
```
