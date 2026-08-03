#!/usr/bin/env bash
# =============================================================================
# 部署后端到端冒烟测试
# -----------------------------------------------------------------------------
# 验证：容器状态 → 健康探针 → 登录鉴权 → 核心接口 → 决策链路 → 事件落库
#
# 用法：
#   bash deploy/scripts/smoke-test.sh
#   ADMIN_USER=admin ADMIN_PASS=xxx bash deploy/scripts/smoke-test.sh
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env.production}"
COMPOSE="$REPO_ROOT/deploy/docker-compose.prod.yml"

[[ -f "$ENV_FILE" ]] || { echo "缺少 $ENV_FILE" >&2; exit 1; }

UI_PORT="$(grep -oP '^UI_PUBLISH_PORT=\K.*'      "$ENV_FILE" || echo 8080)"
GW_PORT="$(grep -oP '^GATEWAY_PUBLISH_PORT=\K.*' "$ENV_FILE" || echo 8000)"
CH_PASS="$(grep -oP '^CLICKHOUSE_PASSWORD=\K.*'  "$ENV_FILE" || echo '')"

UI="http://127.0.0.1:${UI_PORT}"
GW="http://127.0.0.1:${GW_PORT}"

PASS=0; FAIL=0
ok()  { printf '\033[32m  ✓ %s\033[0m\n' "$*"; PASS=$((PASS+1)); }
no()  { printf '\033[31m  ✗ %s\033[0m\n' "$*"; FAIL=$((FAIL+1)); }
sec() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ─────────────────────────────────────────────────────────────
sec "1. 容器运行状态"
for c in fangyu-redis fangyu-mysql fangyu-clickhouse \
         fangyu-gateway fangyu-admin fangyu-worker fangyu-ui; do
    state="$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo missing)"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$c" 2>/dev/null || echo none)"
    if [[ "$state" == "running" ]]; then
        if [[ "$health" == "healthy" || "$health" == "none" ]]; then
            ok "$c running/$health"
        else
            no "$c running 但健康状态为 $health"
        fi
    else
        no "$c 状态 $state"
    fi
done

# 重启次数：反复重启说明启动即崩，日志可能已被轮转掉
sec "2. 容器稳定性"
for c in fangyu-gateway fangyu-admin fangyu-worker; do
    rc="$(docker inspect -f '{{.RestartCount}}' "$c" 2>/dev/null || echo -1)"
    if [[ "$rc" == "0" ]]; then
        ok "$c 未发生重启"
    elif [[ "$rc" -gt 0 ]]; then
        no "$c 已重启 $rc 次，检查 docker logs $c"
    fi
done

# ─────────────────────────────────────────────────────────────
sec "3. 健康探针"
probe() {
    local url="$1" name="$2"
    local code
    code="$(curl -o /dev/null -sw '%{http_code}' --max-time 8 "$url" 2>/dev/null)"
    [[ "$code" == "200" ]] && ok "$name ($code)" || no "$name 返回 $code"
}
probe "$GW/v2/healthz"     "gateway liveness"
probe "$GW/v2/readyz"      "gateway readiness"
probe "$UI/healthz"        "dashboard-ui"
probe "$UI/api/v2/healthz" "admin-api 经 UI 反代"

# ─────────────────────────────────────────────────────────────
sec "4. 前端静态资源"
# 前端用 hash 路由（createWebHashHistory），路径部分恒为 /，
# 所以这里验证的是首页可达与 index.html 正常返回。
CODE="$(curl -o /dev/null -sw '%{http_code}' --max-time 8 "$UI/" 2>/dev/null)"
[[ "$CODE" == "200" ]] && ok "首页返回 200" || no "首页返回 $CODE"

if curl -s --max-time 8 "$UI/" 2>/dev/null | grep -q '<div id="app">'; then
    ok "index.html 内容正常"
else
    no "index.html 未包含挂载点，构建产物可能异常"
fi

# gzip 生效性
if curl -sI -H 'Accept-Encoding: gzip' --max-time 8 "$UI/" 2>/dev/null \
    | grep -qi 'content-encoding: gzip'; then
    ok "gzip 压缩已生效"
else
    # index.html 通常小于 gzip_min_length，不算失败
    printf '\033[33m  ! 首页未返回 gzip（文件可能小于 1k 阈值）\033[0m\n'
fi

# 安全响应头
HEADERS="$(curl -sI --max-time 8 "$UI/" 2>/dev/null)"
for h in x-frame-options x-content-type-options referrer-policy; do
    echo "$HEADERS" | grep -qi "$h" && ok "响应头 $h" || no "缺少响应头 $h"
done

# ─────────────────────────────────────────────────────────────
sec "5. 鉴权链路"

# 未带 token 访问受保护接口必须 401，返回 200 说明鉴权被绕过
CODE="$(curl -o /dev/null -sw '%{http_code}' --max-time 8 "$UI/api/v2/auth/me" 2>/dev/null)"
if [[ "$CODE" == "401" || "$CODE" == "403" ]]; then
    ok "未鉴权访问被拒绝 ($CODE)"
else
    no "未鉴权访问 /v2/auth/me 返回 $CODE，预期 401/403"
fi

# 登录（提供凭据时才测）
if [[ -n "${ADMIN_USER:-}" && -n "${ADMIN_PASS:-}" ]]; then
    RESP="$(curl -s --max-time 10 -X POST "$UI/api/v2/auth/login" \
            -H 'Content-Type: application/json' \
            -d "{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASS}\"}" 2>/dev/null)"
    TOKEN="$(echo "$RESP" | grep -oP '"access_token"\s*:\s*"\K[^"]+' | head -1)"
    if [[ -n "$TOKEN" ]]; then
        ok "登录成功，已获取 access_token"

        auth_probe() {
            local path="$1" name="$2" code
            code="$(curl -o /dev/null -sw '%{http_code}' --max-time 10 \
                    -H "Authorization: Bearer $TOKEN" "$UI/api/v2/$path" 2>/dev/null)"
            [[ "$code" == "200" ]] && ok "$name" || no "$name 返回 $code"
        }
        auth_probe "auth/me"      "当前用户信息"
        auth_probe "sites"        "站点列表"
        auth_probe "rules"        "规则列表"
        auth_probe "users"        "用户列表"
        auth_probe "roles"        "角色列表"
        auth_probe "permissions"  "权限列表"
        auth_probe "access-logs?page=1&page_size=1" "决策日志（ClickHouse 连通性）"
        auth_probe "audit-logs?page=1&page_size=1"  "审计日志"
    else
        no "登录失败。响应：$(echo "$RESP" | head -c 200)"
    fi
else
    printf '\033[33m  ! 跳过登录测试（未设置 ADMIN_USER / ADMIN_PASS）\033[0m\n'
fi

# ─────────────────────────────────────────────────────────────
sec "6. 决策网关"

# 不带 App Key 必须被拒（GATEWAY_APP_KEY_REQUIRED=true）。
# 若返回 200，说明鉴权配置失效，任何人都能刷决策接口。
CODE="$(curl -o /dev/null -sw '%{http_code}' --max-time 8 -X POST "$GW/v2/decide" \
        -H 'Content-Type: application/json' -d '{}' 2>/dev/null)"
case "$CODE" in
    401|403) ok "无 App Key 的决策请求被拒绝 ($CODE)" ;;
    422)     ok "请求体校验生效 ($CODE)" ;;
    200)     no "无 App Key 竟返回 200，App Key 校验未生效" ;;
    *)       no "决策接口返回异常状态 $CODE" ;;
esac

# metrics 不应暴露在网关发布端口之外（此处走回环，正常可访问）
probe "$GW/v2/metrics" "Prometheus 指标端点"

# ─────────────────────────────────────────────────────────────
sec "7. 数据链路"

# Redis Stream 是否已建立消费组：worker 没建组意味着事件不会被消费
GROUP="$(docker exec fangyu-redis sh -c \
    'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning XINFO GROUPS fangyu:events:decision 2>/dev/null' \
    2>/dev/null | head -20)"
if echo "$GROUP" | grep -q 'fangyu-worker'; then
    ok "Redis Stream 消费组 fangyu-worker 已建立"
else
    printf '\033[33m  ! 消费组未建立（尚无决策事件时属正常）\033[0m\n'
fi

# ClickHouse 表存在性
TABLES="$(docker exec fangyu-clickhouse clickhouse-client \
    --user default --password "$CH_PASS" \
    --query "SELECT name FROM system.tables WHERE database='fangyu'" 2>/dev/null)"
for t in decision_events decision_traces; do
    echo "$TABLES" | grep -qx "$t" && ok "ClickHouse 表 fangyu.$t" || no "缺少表 fangyu.$t"
done

# MySQL 迁移版本
VER="$(docker compose -f "$COMPOSE" --env-file "$ENV_FILE" \
       exec -T admin-api alembic current 2>/dev/null | tail -1)"
[[ -n "$VER" ]] && ok "Alembic 版本：$VER" || no "无法读取 Alembic 版本"

# ─────────────────────────────────────────────────────────────
sec "8. 日志与持久化"

for v in redis-data mysql-data clickhouse-data mmdb-data; do
    if docker volume ls --format '{{.Name}}' | grep -q "${v}$"; then
        ok "数据卷 $v 存在"
    else
        no "缺少数据卷 $v"
    fi
done

# 日志轮转：未配置时单个容器日志可能撑满磁盘
# Go 模板里含连字符的 key 不能用点号取（max-size 会被当作减法），必须走 index。
LOG_OPT="$(docker inspect -f '{{index .HostConfig.LogConfig.Config "max-size"}}' fangyu-gateway 2>/dev/null)"
[[ -n "$LOG_OPT" ]] && ok "日志轮转已配置（max-size=$LOG_OPT）" || no "未配置日志轮转"

# ─────────────────────────────────────────────────────────────
printf '\n\033[1m== 汇总 ==\033[0m\n'
printf '通过 %d，失败 %d\n' "$PASS" "$FAIL"
[[ "$FAIL" == "0" ]] && exit 0 || exit 1
