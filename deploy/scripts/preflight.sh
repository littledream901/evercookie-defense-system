#!/usr/bin/env bash
# =============================================================================
# 部署前环境检查
# -----------------------------------------------------------------------------
# 只读脚本，不修改任何状态。检查失败项会累计并在结尾汇总。
#
# 用法：bash deploy/scripts/preflight.sh
# 退出码：0 全部通过；1 存在阻塞项
# =============================================================================
set -uo pipefail

# REPO_ROOT 优先取外部注入，避免 deploy.sh 与直接调用时定位不一致
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env.production}"

# 磁盘门槛可覆盖，用于磁盘受限但已知风险的场景（如小流量试运行）：
#   DISK_MIN_GB=20 bash deploy/deploy.sh init
# 默认值不变，覆盖是显式行为，不影响其他人的部署检查。
DISK_MIN_GB="${DISK_MIN_GB:-50}"
DISK_RECOMMEND_GB="${DISK_RECOMMEND_GB:-100}"

COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/deploy/docker-compose.prod.yml}"

FAIL=0
WARN=0

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

ok()    { green  "  [PASS] $*"; }
bad()   { red    "  [FAIL] $*"; FAIL=$((FAIL+1)); }
warn()  { yellow "  [WARN] $*"; WARN=$((WARN+1)); }

section() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# ─────────────────────────────────────────────────────────────
section "1. 运行时组件"

if command -v docker >/dev/null 2>&1; then
    DOCKER_VER="$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "")"
    if [[ -z "$DOCKER_VER" ]]; then
        bad "Docker 已安装但守护进程无响应（检查 systemctl status docker）"
    else
        ok "Docker $DOCKER_VER"
        # 需要 >= 24：compose v2 的 depends_on.condition 与 healthcheck 语义依赖此版本
        if [[ "${DOCKER_VER%%.*}" -lt 24 ]]; then
            warn "Docker 版本低于 24，建议升级"
        fi
    fi
else
    bad "未安装 Docker"
fi

if docker compose version >/dev/null 2>&1; then
    ok "docker compose $(docker compose version --short 2>/dev/null)"
else
    bad "docker compose v2 插件不可用（本项目不支持 docker-compose v1）"
fi

# ─────────────────────────────────────────────────────────────
section "2. 系统资源"

CPU_CORES="$(nproc 2>/dev/null || echo 0)"
if [[ "$CPU_CORES" -ge 4 ]]; then
    ok "CPU ${CPU_CORES} 核"
elif [[ "$CPU_CORES" -ge 2 ]]; then
    warn "CPU 仅 ${CPU_CORES} 核，需下调 GATEWAY_WORKERS / ADMIN_WORKERS"
else
    bad "CPU ${CPU_CORES} 核，低于最低要求 2 核"
fi

MEM_MB="$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)"
if [[ "$MEM_MB" -ge 8000 ]]; then
    ok "内存 ${MEM_MB} MB"
elif [[ "$MEM_MB" -ge 4000 ]]; then
    warn "内存 ${MEM_MB} MB，偏紧。需下调 MYSQL_BUFFER_POOL 与 REDIS_MAXMEMORY"
else
    bad "内存 ${MEM_MB} MB，低于最低要求 4 GB"
fi

DISK_GB="$(df -BG --output=avail /var/lib/docker 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)"
DISK_GB="${DISK_GB:-0}"
if [[ "$DISK_GB" -ge "$DISK_RECOMMEND_GB" ]]; then
    ok "Docker 数据盘剩余 ${DISK_GB} GB"
elif [[ "$DISK_GB" -ge "$DISK_MIN_GB" ]]; then
    warn "剩余 ${DISK_GB} GB。ClickHouse 日志增长快，建议预留 ${DISK_RECOMMEND_GB} GB 以上"
    [[ "$DISK_MIN_GB" -lt 50 ]] && \
        warn "磁盘门槛已被 DISK_MIN_GB=${DISK_MIN_GB} 放宽（默认 50）。ClickHouse 写满后将拒绝写入，决策日志会丢失"
else
    bad "剩余 ${DISK_GB} GB，低于最低要求 ${DISK_MIN_GB} GB"
fi

# ─────────────────────────────────────────────────────────────
section "3. 端口占用"

# 本项目容器已发布的端口集合。首次部署中途失败后重跑时，数据层容器往往
# 已在运行，其 docker-proxy 持有端口属预期状态，不应判为冲突。
#
# 直接问 compose 要自己的容器，而非猜项目名：deploy.sh 未指定
# --project-name，compose 默认取 compose 文件所在目录名，该值会随目录
# 改名而变，硬编码不可靠。
OWN_PORTS=""
if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
    own_cids="$(
        docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
            ps -q 2>/dev/null || true
    )"
    if [[ -n "$own_cids" ]]; then
        OWN_PORTS="$(
            docker inspect --format '{{range $p, $c := .NetworkSettings.Ports}}{{range $c}}{{.HostPort}}
{{end}}{{end}}' $own_cids 2>/dev/null | grep -E '^[0-9]+$' | sort -u || true
        )"
    fi
fi

# 仅检查本项目要发布的回环端口。80/443 由 1Panel OpenResty 持有，
# 被占用是预期状态，因此单独提示而不判失败。
check_port() {
    local port="$1" desc="$2"
    if ss -tlnH "sport = :$port" 2>/dev/null | grep -q .; then
        if printf '%s\n' "$OWN_PORTS" | grep -qx "$port"; then
            ok "端口 $port（$desc）由本项目容器持有，属预期"
            return
        fi
        local who
        who="$(ss -tlnpH "sport = :$port" 2>/dev/null | grep -oP 'users:\(\("\K[^"]+' | head -1)"
        if [[ "$who" == "docker-proxy" ]]; then
            bad "端口 $port（$desc）被其他 Docker 项目占用。查看归属：docker ps --filter publish=$port"
        else
            bad "端口 $port（$desc）已被占用${who:+：$who}"
        fi
    else
        ok "端口 $port（$desc）空闲"
    fi
}

UI_PORT="$(grep -oP '^UI_PUBLISH_PORT=\K.*'      "$ENV_FILE" 2>/dev/null || echo 8080)"
GW_PORT="$(grep -oP '^GATEWAY_PUBLISH_PORT=\K.*' "$ENV_FILE" 2>/dev/null || echo 8000)"

check_port "${UI_PORT:-8080}" "dashboard-ui"
check_port "${GW_PORT:-8000}" "gateway-api"
check_port 3306 "MySQL"
check_port 6379 "Redis"
check_port 8123 "ClickHouse HTTP"
check_port 9000 "ClickHouse TCP"

for p in 80 443; do
    if ss -tlnH "sport = :$p" 2>/dev/null | grep -q .; then
        ok "端口 $p 已被占用（应为 1Panel OpenResty，属预期）"
    else
        warn "端口 $p 未监听 —— 确认 1Panel OpenResty 已启动"
    fi
done

# ─────────────────────────────────────────────────────────────
section "4. 环境变量文件"

if [[ ! -f "$ENV_FILE" ]]; then
    bad "缺少 $ENV_FILE（从 .env.production.example 复制并填写）"
else
    ok "找到 $ENV_FILE"

    PERM="$(stat -c '%a' "$ENV_FILE")"
    if [[ "$PERM" == "600" || "$PERM" == "400" ]]; then
        ok "文件权限 $PERM"
    else
        bad "文件权限 $PERM 过宽，含明文口令，执行 chmod 600 $ENV_FILE"
    fi

    # 未替换的占位符
    if grep -q '__REPLACE_' "$ENV_FILE"; then
        bad "存在未替换的占位符："
        grep -n '__REPLACE_' "$ENV_FILE" | sed 's/=.*/=<未填写>/' | sed 's/^/         /'
    else
        ok "无未替换占位符"
    fi

    # 必填项
    for key in MYSQL_ROOT_PASSWORD MYSQL_PASSWORD REDIS_PASSWORD \
               CLICKHOUSE_PASSWORD ADMIN_JWT_SECRET \
               ADMIN_DATABASE_URL ADMIN_REDIS_URL GATEWAY_REDIS_URL \
               WORKER_REDIS_URL ADMIN_CORS_ORIGINS GATEWAY_CORS_ORIGINS; do
        val="$(grep -oP "^${key}=\K.*" "$ENV_FILE" 2>/dev/null || true)"
        if [[ -z "$val" ]]; then
            bad "$key 未设置或为空"
        fi
    done

    # JWT 密钥强度：AdminSettings 要求 min_length=8，但生产下限按 32 卡
    JWT="$(grep -oP '^ADMIN_JWT_SECRET=\K.*' "$ENV_FILE" 2>/dev/null || true)"
    if [[ -n "$JWT" ]]; then
        if [[ "${#JWT}" -ge 32 ]]; then
            ok "ADMIN_JWT_SECRET 长度 ${#JWT}"
        else
            bad "ADMIN_JWT_SECRET 长度仅 ${#JWT}，生产要求 >= 32"
        fi
        case "$JWT" in
            *change-me*|*please-change*|*local-dev*)
                bad "ADMIN_JWT_SECRET 仍是示例值" ;;
        esac
    fi

    # CORS 必须是 JSON 数组：pydantic 的 list[str] 无法解析逗号分隔串，
    # 配错会让服务在启动时直接崩。
    # ADMIN_CORS_ORIGINS 是后台管理接口，严禁通配；
    # GATEWAY_CORS_ORIGINS 面向 SDK 公开接入，允许 "*"，但需注意与 allow_credentials 的兼容性。
    for key in ADMIN_CORS_ORIGINS GATEWAY_CORS_ORIGINS; do
        val="$(grep -oP "^${key}=\K.*" "$ENV_FILE" 2>/dev/null || true)"
        [[ -z "$val" ]] && continue
        if [[ "$val" == \[*\] ]]; then
            if [[ "$val" == *'"*"'* ]]; then
                if [[ "$key" == "GATEWAY_CORS_ORIGINS" ]]; then
                    warn "$key 含通配 \"*\"，请确保网关应用层已关闭 allow_credentials"
                else
                    bad "$key 含通配 \"*\"，生产不允许（与 allow_credentials 冲突）"
                fi
            else
                ok "$key 格式为 JSON 数组"
            fi
        else
            bad "$key 必须是 JSON 数组，如 [\"https://a.com\"]，当前为：$val"
        fi
    done

    # 连接串主机名：容器内 localhost 指向容器自身，必然连不通
    for key in ADMIN_DATABASE_URL ADMIN_REDIS_URL GATEWAY_REDIS_URL WORKER_REDIS_URL; do
        val="$(grep -oP "^${key}=\K.*" "$ENV_FILE" 2>/dev/null || true)"
        if [[ "$val" == *localhost* || "$val" == *127.0.0.1* ]]; then
            bad "$key 指向 localhost，容器内应使用服务名（mysql / redis / clickhouse）"
        fi
    done

    # Stream 名一致性：gateway 写入与 worker 消费必须同名，否则事件永不落库
    if grep -q '^STREAM_NAME=' "$ENV_FILE"; then
        ok "STREAM_NAME 已统一配置"
    else
        warn "未显式设置 STREAM_NAME，将使用默认 fangyu:events:decision"
    fi
fi

# ─────────────────────────────────────────────────────────────
section "5. 编排与前端配置"

# 使用已设置的 COMPOSE_FILE，避免重复计算
if [[ -f "$COMPOSE_FILE" ]]; then
    if [[ -f "$ENV_FILE" ]] && \
       docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config -q 2>/dev/null; then
        ok "docker-compose.prod.yml 语法与变量插值通过"
    else
        bad "compose 配置校验失败，详情："
        docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config -q 2>&1 \
            | head -20 | sed 's/^/         /'
    fi
else
    bad "缺少 $COMPOSE_FILE"
fi

# 网关域名权威源：.env.production 的 GATEWAY_DOMAIN。
# 前端 .env.production 由 deploy.sh 从这里同步，UI 侧值必须与之一致。
if [[ -f "$ENV_FILE" ]]; then
    GW_DOMAIN="$(grep -oP '^GATEWAY_DOMAIN=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' | sed 's|/$||')"
    if [[ -z "$GW_DOMAIN" ]]; then
        bad ".env.production 缺少 GATEWAY_DOMAIN，前端接入指引将显示占位地址"
    elif echo "$GW_DOMAIN" | grep -q 'example\.com'; then
        bad "GATEWAY_DOMAIN 仍是示例值 ($GW_DOMAIN)，请改为实际网关域名"
    else
        ok "GATEWAY_DOMAIN=$GW_DOMAIN"
    fi
fi

# 前端生产配置：Mock 地址混入生产是最容易漏的一项
UI_ENV="$REPO_ROOT/dashboard-ui/.env.production"
if [[ -f "$UI_ENV" ]]; then
    if grep -qi 'apifoxmock\|mock' "$UI_ENV"; then
        bad "dashboard-ui/.env.production 仍指向 Mock 服务"
    else
        ok "前端生产配置未包含 Mock 地址"
    fi
    if grep -q 'defense.example.com\|example.com' "$UI_ENV"; then
        bad "dashboard-ui/.env.production 的 VITE_GATEWAY_URL 仍是示例域名"
        echo "         修复：编辑 .env.production 设 GATEWAY_DOMAIN，再重跑 deploy.sh"
    else
        ok "VITE_GATEWAY_URL 已替换为实际域名"
    fi

    # 交叉校验：UI 侧值必须与后端 GATEWAY_DOMAIN 完全一致，否则说明
    # 之前跳过了 sync_gateway_url_to_ui 或有人手工改过一边没改另一边
    if [[ -n "${GW_DOMAIN:-}" ]] && ! echo "$GW_DOMAIN" | grep -q 'example\.com'; then
        UI_GW="$(grep -oP '^VITE_GATEWAY_URL\s*=\s*\K.*' "$UI_ENV" 2>/dev/null | tr -d '"' | sed 's|/$||' | xargs)"
        if [[ "$UI_GW" != "$GW_DOMAIN" ]]; then
            bad "VITE_GATEWAY_URL ($UI_GW) 与 GATEWAY_DOMAIN ($GW_DOMAIN) 不一致"
            echo "         修复：重跑 deploy.sh init 或手工同步两处"
        else
            ok "前后端网关地址一致"
        fi
    fi
else
    bad "缺少 dashboard-ui/.env.production"
fi

# ─────────────────────────────────────────────────────────────
section "6. 镜像与代码"

if [[ -f "$ENV_FILE" ]]; then
    TAG="$(grep -oP '^IMAGE_TAG=\K.*' "$ENV_FILE" 2>/dev/null || true)"
    if [[ "$TAG" == "latest" || -z "$TAG" ]]; then
        bad "IMAGE_TAG 为 latest 或未设置，回滚将无法定位版本"
    else
        ok "IMAGE_TAG=$TAG"
    fi
fi

if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
    ok "当前分支 $BRANCH @ $(git -C "$REPO_ROOT" rev-parse --short HEAD)"
    if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
        warn "工作区有未提交改动，构建产物将与 Git 记录不一致"
    fi
fi

# ─────────────────────────────────────────────────────────────
section "7. 备份就绪"

BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/deploy/backups}"
if [[ -d "$BACKUP_DIR" ]]; then
    ok "备份目录存在：$BACKUP_DIR"
else
    warn "备份目录不存在，backup.sh 首次运行时会自动创建"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^fangyu-mysql$'; then
    ok "MySQL 容器在运行，可执行部署前全量备份"
else
    warn "MySQL 容器未运行（首次部署属正常，升级部署则必须先备份）"
fi

# ─────────────────────────────────────────────────────────────
printf '\n\033[1m== 汇总 ==\033[0m\n'
if [[ "$FAIL" -eq 0 ]]; then
    green "阻塞项 0，警告 $WARN —— 具备部署条件"
    exit 0
else
    red "阻塞项 $FAIL，警告 $WARN —— 修复后重跑本脚本"
    exit 1
fi
