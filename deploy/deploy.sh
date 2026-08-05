#!/usr/bin/env bash
# =============================================================================
#  Evercookie Defense System V2 — 一键部署与运维入口
# -----------------------------------------------------------------------------
#  生命周期：
#    clone   → 克隆代码并转入 init
#    init    → 生成配置 → 预检 → 构建 → 启动 → 迁移 → 验收
#    update  → 拉取代码 → 备份 → 构建 → 滚动重启 → 验收
#    status / logs / restart / stop / backup / rollback / verify
#
#  与 deploy/scripts/*.sh 的关系：本脚本是统一入口，
#  预检、备份、回滚、冒烟测试等复用 scripts/ 下的实现，不重复逻辑。
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

COMPOSE_FILE="$SCRIPT_DIR/docker-compose.prod.yml"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.production}"
ENV_TEMPLATE="$PROJECT_DIR/.env.production.example"
UI_ENV_FILE="$PROJECT_DIR/dashboard-ui/.env.production"

GIT_REPO="${GIT_REPO:-}"
GIT_BRANCH="${GIT_BRANCH:-main}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

LOG_TAIL_LINES="${LOG_TAIL_LINES:-20}"
ANIMATION_THRESHOLD="${ANIMATION_THRESHOLD:-8}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/.logs}"
STEP_INDEX=0

# ──────────────────── 输出 ────────────────────

log()  { echo -e "  ├─ ${GREEN}[INFO]${NC}  $1"; }
warn() { echo -e "  ├─ ${YELLOW}[WARN]${NC}  $1"; }
err()  { echo -e "  └─ ${RED}[ERROR]${NC} $1" >&2; exit 1; }

section() {
    echo ""
    echo -e "${CYAN}══ $1 ══${NC}"
}

elapsed_seconds() { echo $(( $(date +%s) - $1 )); }

step_begin() {
    STEP_INDEX=$((STEP_INDEX + 1))
    echo ""
    echo -e "${CYAN}▶ [${STEP_INDEX}] $1${NC}"
    echo -e "  ├─ 状态: ${BLUE}开始${NC}"
}

step_finish() {
    if [ "$1" -eq 0 ]; then
        echo -e "  └─ 状态: ${GREEN}完成${NC} (${2}s)"
    else
        echo -e "  └─ 状态: ${RED}失败${NC} (${2}s)"
    fi
}

safe_log_name() { echo "$1" | tr -cs '[:alnum:]' '_' | cut -c1-48; }

show_log_tail() {
    local log_file="$1" lines="${2:-$LOG_TAIL_LINES}"
    [ -s "$log_file" ] || return 0
    echo -e "  ├─ 最近 ${lines} 行日志:"
    tail -n "$lines" "$log_file" | sed 's/^/  │  /'
}

# 长任务转圈：仅在交互式终端且超过阈值后显示，CI 环境自动退化为静默
animate_wait() {
    local pid="$1" title="$2" start_ts="$3"
    local frame_index=0
    local spinner='|/-\'
    while kill -0 "$pid" 2>/dev/null; do
        local elapsed
        elapsed=$(elapsed_seconds "$start_ts")
        if [ "$elapsed" -ge "$ANIMATION_THRESHOLD" ] && [ -t 1 ] && [ "${NO_ANIMATION:-0}" != "1" ]; then
            local frame="${spinner:$frame_index:1}"
            frame_index=$(((frame_index + 1) % 4))
            printf "\r\033[K  ├─ 执行中: %s %s (%ss)" "$frame" "$title" "$elapsed"
        fi
        sleep 1
    done
    if [ -t 1 ] && [ "${NO_ANIMATION:-0}" != "1" ]; then printf "\r\033[K"; fi
}

# 后台执行并落盘日志。失败时只显示尾部日志，完整内容留在 $LOG_DIR。
run_step() {
    local title="$1"; shift
    mkdir -p "$LOG_DIR"
    local log_file="${LOG_DIR}/$(date +%Y%m%d%H%M%S)_$(safe_log_name "$title").log"
    local start_ts
    start_ts=$(date +%s)

    step_begin "$title"
    "$@" >"$log_file" 2>&1 &
    local pid=$!
    animate_wait "$pid" "$title" "$start_ts"

    local status=0
    wait "$pid" || status=$?
    local elapsed
    elapsed=$(elapsed_seconds "$start_ts")
    if [ "$status" -ne 0 ]; then
        show_log_tail "$log_file" "$LOG_TAIL_LINES"
        echo -e "  ├─ 完整日志: $log_file"
    fi
    step_finish "$status" "$elapsed"
    return "$status"
}

# 需要实时输出的步骤（如迁移、预检）直接前台跑。
# 输出经 sed 缩进，但退出码必须取管道左侧——sed 几乎总是成功，
# 直接读管道退出码会把失败当成功。
run_fg() {
    local title="$1"; shift
    local start_ts
    start_ts=$(date +%s)
    step_begin "$title"

    local status_file
    status_file="$(mktemp)"
    { "$@" 2>&1; echo "$?" > "$status_file"; } | sed 's/^/  │  /'
    local status
    status="$(cat "$status_file")"
    rm -f "$status_file"

    step_finish "$status" "$(elapsed_seconds "$start_ts")"
    return "$status"
}

# ──────────────────── Compose 封装 ────────────────────

# 本项目要求 compose v2：depends_on.condition: service_healthy 与
# deploy.resources 在 v1 下不生效，静默降级会导致启动顺序错乱。
dc() {
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

check_deps() {
    command -v docker >/dev/null 2>&1 || err "未安装 Docker，需 24.0+"
    docker version >/dev/null 2>&1 || err "Docker 守护进程无响应：systemctl status docker"
    docker compose version >/dev/null 2>&1 \
        || err "docker compose v2 插件不可用（本项目不支持 docker-compose v1）"
    command -v curl >/dev/null 2>&1 || err "未安装 curl"
    command -v git  >/dev/null 2>&1 || warn "未安装 git，update 命令将无法拉取代码"
    log "依赖检查通过（Docker $(docker version --format '{{.Server.Version}}')）"
}

read_env() {
    local key="$1" default_value="${2:-}"
    [ -f "$ENV_FILE" ] || { echo "$default_value"; return; }
    local val
    val="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d '=' -f2-)"
    echo "${val:-$default_value}"
}

ui_port()      { read_env UI_PUBLISH_PORT 8080; }
gateway_port() { read_env GATEWAY_PUBLISH_PORT 8000; }

require_env_file() {
    [ -f "$ENV_FILE" ] || err "缺少 $ENV_FILE，先执行：bash deploy/deploy.sh init"
}

# ──────────────────── 健康等待 ────────────────────

wait_http() {
    local name="$1" url="$2" max_sec="${3:-120}" svc="${4:-}"
    local waited=0 code="" last=""

    echo -n "  等待 ${name} ..."
    while [ "$waited" -lt "$max_sec" ]; do
        code="$(curl -o /dev/null -sw '%{http_code}' --connect-timeout 3 --max-time 8 "$url" 2>/dev/null || echo 000)"
        if [ "$code" = "200" ]; then
            echo -e " ${GREEN}就绪${NC}"
            return 0
        fi
        [ "$code" = "000" ] && last="连接被拒绝" || last="HTTP ${code}"
        printf "."
        sleep 3
        waited=$((waited + 3))
    done

    echo ""
    warn "${name} 健康检查超时 (${max_sec}s)，最后状态: ${last}"
    if [ -n "$svc" ]; then
        echo "  ── ${svc} 最近日志 ──"
        dc logs --tail 25 "$svc" 2>/dev/null | sed 's/^/  │  /' || true
    fi
    return 1
}

wait_container() {
    local svc="$1" max_sec="${2:-180}"
    local waited=0

    echo -n "  等待容器 ${svc} ..."
    while [ "$waited" -lt "$max_sec" ]; do
        local cid state
        cid="$(dc ps -q "$svc" 2>/dev/null || true)"
        if [ -n "$cid" ]; then
            # 有 healthcheck 时看健康状态，没有则看运行状态
            state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
            if [ "$state" = "healthy" ] || [ "$state" = "running" ]; then
                echo -e " ${GREEN}就绪${NC}"
                return 0
            fi
            if [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
                echo ""
                warn "${svc} 容器已退出"
                dc logs --tail 30 "$svc" 2>/dev/null | sed 's/^/  │  /' || true
                return 1
            fi
        fi
        printf "."
        sleep 3
        waited=$((waited + 3))
    done

    echo ""
    warn "${svc} 未在 ${max_sec}s 内就绪"
    dc logs --tail 30 "$svc" 2>/dev/null | sed 's/^/  │  /' || true
    return 1
}

# 数据层就绪后才起应用层。gateway/admin 启动即连 Redis/MySQL/CH，
# 提前起会反复重启直到 restart 上限。
wait_data_layer() {
    wait_container redis      90  || return 1
    wait_container mysql      240 || return 1
    wait_container clickhouse 180 || return 1
}

verify_endpoints() {
    local ui gw fail=0
    ui="$(ui_port)"; gw="$(gateway_port)"

    wait_http "gateway-api"        "http://127.0.0.1:${gw}/v2/healthz"    90 gateway-api  || fail=1
    wait_http "gateway readiness"  "http://127.0.0.1:${gw}/v2/readyz"     60 gateway-api  || fail=1
    wait_http "dashboard-ui"       "http://127.0.0.1:${ui}/healthz"       60 dashboard-ui || fail=1
    # 经 UI 容器内 Nginx 反代，等价于验证前端到 admin-api 的完整链路
    wait_http "admin-api"          "http://127.0.0.1:${ui}/api/v2/healthz" 90 admin-api   || fail=1

    if dc exec -T worker curl -fsS --max-time 5 http://127.0.0.1:9091/healthz >/dev/null 2>&1; then
        echo -e "  worker ... ${GREEN}就绪${NC}"
    else
        warn "worker 探活失败"
        dc logs --tail 25 worker 2>/dev/null | sed 's/^/  │  /' || true
        fail=1
    fi
    return "$fail"
}

# ──────────────────── clone ────────────────────

cmd_clone() {
    local target_dir="${1:-fangyu}"
    local repo_url="${2:-$GIT_REPO}"

    [ -n "$repo_url" ] || err "未指定仓库地址。用法：bash deploy/deploy.sh clone <目录> <仓库地址>
或先设置环境变量：export GIT_REPO=https://..."

    section "克隆项目代码"
    command -v git >/dev/null 2>&1 || err "未安装 git"

    if [ -d "$target_dir/.git" ]; then
        warn "目录 $target_dir 已是 Git 仓库，跳过克隆"
    elif [ -d "$target_dir" ] && [ -n "$(ls -A "$target_dir" 2>/dev/null)" ]; then
        err "目录 $target_dir 已存在且非空，请换目录或手工清理"
    else
        run_step "克隆 $repo_url ($GIT_BRANCH)" \
            git clone --branch "$GIT_BRANCH" --depth 1 "$repo_url" "$target_dir" \
            || err "克隆失败，检查仓库地址、分支名与网络"
    fi

    cd "$target_dir"
    log "代码位于 $(pwd)"
    # 转交给新检出目录里的脚本，避免用旧脚本跑新代码
    exec bash deploy/deploy.sh init
}

# ──────────────────── 配置准备 ────────────────────

# 生成 .env.production。已存在则不动——覆盖会导致 MySQL 数据卷里的
# 旧口令与新配置不匹配，服务连不上库。
prepare_env_file() {
    if [ -f "$ENV_FILE" ]; then
        log "$ENV_FILE 已存在，保留现有配置"
        chmod 600 "$ENV_FILE"
        return 0
    fi

    [ -f "$ENV_TEMPLATE" ] || err "缺少模板 $ENV_TEMPLATE"

    log "从模板生成 $ENV_FILE"
    bash "$SCRIPTS_DIR/gen-secrets.sh" || err "生成凭据失败"
}

# 从 .env.production 的 GATEWAY_DOMAIN 同步到 VITE_GATEWAY_URL
# 确保前后端使用同一个网关地址
sync_gateway_url_to_ui() {
    [ -f "$ENV_FILE" ] || return 0

    local gateway_url
    gateway_url="$(grep -oP '^GATEWAY_DOMAIN=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' | sed 's|/$||')"

    if [ -z "$gateway_url" ] || echo "$gateway_url" | grep -q 'example\.com'; then
        warn "GATEWAY_DOMAIN 未配置或仍是示例值，前端接入指引会显示占位地址"
        echo "    请编辑 $ENV_FILE 设置 GATEWAY_DOMAIN=https://<你的网关域名>"
        return 0
    fi

    # 直接在 .env.production 中更新 VITE_GATEWAY_URL
    if grep -q '^VITE_GATEWAY_URL=' "$ENV_FILE"; then
        sed -i "s|^VITE_GATEWAY_URL=.*|VITE_GATEWAY_URL=${gateway_url}|" "$ENV_FILE"
    else
        echo "VITE_GATEWAY_URL=${gateway_url}" >> "$ENV_FILE"
    fi
    
    log "VITE_GATEWAY_URL → ${gateway_url}"
}

# 交互式收集域名。非交互环境（CI / 管道）跳过，由用户自行编辑。
collect_domains() {
    if [ ! -t 0 ] || [ "${NON_INTERACTIVE:-0}" = "1" ]; then
        warn "非交互模式，跳过域名配置。请手工编辑以下项："
        echo "    $ENV_FILE      → GATEWAY_DOMAIN / ADMIN_CORS_ORIGINS / GATEWAY_CORS_ORIGINS"
        echo "    编辑完成后重跑 deploy.sh 会自动把 GATEWAY_DOMAIN 同步到前端"
        sync_gateway_url_to_ui
        return 0
    fi

    # 已配置过就不再问
    if ! grep -q 'example\.com' "$ENV_FILE" 2>/dev/null; then
        log "域名已配置，跳过"
        sync_gateway_url_to_ui
        return 0
    fi

    echo ""
    echo -e "${YELLOW}配置访问域名${NC}（直接回车跳过，稍后手工编辑）"
    local admin_domain gateway_domain biz_domains

    read -rp "  管理后台域名（如 admin.example.com）: " admin_domain
    read -rp "  决策网关域名（如 defense.example.com）: " gateway_domain
    read -rp "  接入 SDK 的业务域名（多个用空格分隔）: " biz_domains

    if [ -n "$admin_domain" ]; then
        sed -i "s|^ADMIN_CORS_ORIGINS=.*|ADMIN_CORS_ORIGINS=[\"https://${admin_domain}\"]|" "$ENV_FILE"
        log "ADMIN_CORS_ORIGINS → https://${admin_domain}"
    fi

    if [ -n "$biz_domains" ]; then
        # 拼 JSON 数组：pydantic 的 list[str] 只接受 JSON，逗号分隔串会解析失败
        local json="["
        local first=1
        for d in $biz_domains; do
            [ "$first" -eq 1 ] && first=0 || json+=","
            json+="\"https://${d}\""
        done
        json+="]"
        sed -i "s|^GATEWAY_CORS_ORIGINS=.*|GATEWAY_CORS_ORIGINS=${json}|" "$ENV_FILE"
        log "GATEWAY_CORS_ORIGINS → ${json}"
    fi

    if [ -n "$gateway_domain" ]; then
        # 写入后端权威源
        sed -i "s|^GATEWAY_DOMAIN=.*|GATEWAY_DOMAIN=https://${gateway_domain}|" "$ENV_FILE"
        log "GATEWAY_DOMAIN → https://${gateway_domain}"
    fi

    # 无论交互输入了什么，最后统一从后端 .env.production 同步到前端
    sync_gateway_url_to_ui
}

# ──────────────────── init ────────────────────

cmd_init() {
    section "首次部署"
    cd "$PROJECT_DIR"
    check_deps

    prepare_env_file
    collect_domains

    # 预检不通过就停，不要带着已知问题往下走
    # 显式导出路径变量，避免子脚本因 BASH_SOURCE 展开位置不同而误判仓库根
    if ! REPO_ROOT="$PROJECT_DIR" ENV_FILE="$ENV_FILE" COMPOSE_FILE="$COMPOSE_FILE" \
        run_fg "环境预检" bash "$SCRIPTS_DIR/preflight.sh"; then
        err "预检未通过。修复上述阻塞项后重跑：bash deploy/deploy.sh init"
    fi

    # 只拉数据层的第三方镜像。业务服务带 build 段，其 image 名在仓库里不存在，
    # 一并 pull 会报错。
    run_step "拉取基础镜像" dc pull redis mysql clickhouse \
        || warn "基础镜像拉取失败，启动时会重试"

    DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 \
        run_step "构建业务镜像" dc build --pull || err "镜像构建失败"

    run_step "启动数据层" dc up -d redis mysql clickhouse || err "数据层启动失败"

    section "等待数据层就绪"
    wait_data_layer || err "数据层未能就绪，检查日志：bash deploy/deploy.sh logs mysql"

    run_step "启动应用层" dc up -d || err "应用层启动失败"

    # 迁移用临时容器执行，与 update 路径保持一致。
    # alembic 随镜像发布，env.py 读 ADMIN_DATABASE_URL。
    if ! run_fg "数据库迁移" dc run --rm --no-deps admin-api alembic upgrade head; then
        err "迁移失败。首次部署数据为空，可直接排查后重跑"
    fi

    section "启动验收"
    local verify_status=0
    verify_endpoints || verify_status=1

    echo ""
    dc ps

    if [ "$verify_status" -ne 0 ]; then
        echo ""
        echo -e "${RED}部署完成但验收未全部通过${NC}"
        echo "  排查：bash deploy/deploy.sh logs"
        echo "  诊断：bash deploy/deploy.sh doctor"
        exit 1
    fi

    print_success_banner
}

print_success_banner() {
    local ui gw tag
    ui="$(ui_port)"; gw="$(gateway_port)"; tag="$(read_env IMAGE_TAG unknown)"

    echo ""
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}  部署成功  版本 ${tag}${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo "  管理后台（回环）: http://127.0.0.1:${ui}"
    echo "  决策网关（回环）: http://127.0.0.1:${gw}"
    echo ""
    echo -e "  ${YELLOW}容器只监听回环地址，公网访问需在 1Panel OpenResty${NC}"
    echo -e "  ${YELLOW}中创建反代站点。模板见 deploy/openresty/${NC}"
    echo ""
    echo "  待办："
    echo "    1. 配置 OpenResty 站点并申请 SSL 证书"
    echo "    2. 登录后台修改默认管理员口令"
    echo "    3. 配置每日备份：bash deploy/deploy.sh backup"
    echo ""
    echo "  常用命令："
    echo "    状态  bash deploy/deploy.sh status"
    echo "    日志  bash deploy/deploy.sh logs [服务名]"
    echo "    验证  bash deploy/deploy.sh verify"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
}

# ──────────────────── update ────────────────────

cmd_update() {
    section "更新部署"
    cd "$PROJECT_DIR"
    check_deps
    require_env_file

    local old_tag
    old_tag="$(read_env IMAGE_TAG unknown)"

    # 1. 拉代码。.env.production 已在 .gitignore 中，无需备份还原。
    if [ -d ".git" ]; then
        if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
            warn "工作区有未提交改动，跳过 git pull 以免冲突"
        else
            run_step "拉取最新代码（$GIT_BRANCH）" \
                git pull --ff-only origin "$GIT_BRANCH" \
                || warn "拉取失败，使用当前代码继续"
        fi
    else
        warn "非 Git 仓库，跳过拉取代码"
    fi

    log "当前提交：$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

    # 2. 版本号推进。tag 不变会导致回滚无法区分新旧镜像。
    local new_tag
    new_tag="$(read_env IMAGE_TAG unknown)"
    if [ "$new_tag" = "$old_tag" ]; then
        if [ -t 0 ] && [ "${NON_INTERACTIVE:-0}" != "1" ]; then
            echo ""
            warn "IMAGE_TAG 仍为 $old_tag。同 tag 会覆盖旧镜像，回滚将失效。"
            read -rp "  输入新版本号（回车沿用 $old_tag）: " input_tag
            if [ -n "$input_tag" ]; then
                sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${input_tag}|" "$ENV_FILE"
                new_tag="$input_tag"
                log "IMAGE_TAG → $new_tag"
            fi
        else
            warn "IMAGE_TAG 未变更（$old_tag），旧镜像将被覆盖，回滚不可用"
        fi
    fi

    # 3. 更新前必须备份。这是唯一的数据兜底。
    if [ "${SKIP_BACKUP:-0}" = "1" ]; then
        warn "已按 SKIP_BACKUP=1 跳过备份"
    else
        run_fg "更新前全量备份" bash "$SCRIPTS_DIR/backup.sh" \
            || err "备份失败，中止更新"
    fi

    # 4. 记录回滚锚点
    local state_dir="$SCRIPT_DIR/.deploy-state"
    mkdir -p "$state_dir"; chmod 700 "$state_dir"
    [ -f "$state_dir/current.env" ] && cp "$state_dir/current.env" "$state_dir/previous.env"
    {
        echo "IMAGE_TAG=$new_tag"
        echo "GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
        echo "DEPLOY_TIME=$(date -Iseconds)"
    } > "$state_dir/current.env"

    # 5. 构建新镜像，旧容器保持在线
    DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 \
        run_step "构建新镜像 $new_tag" dc build --pull || err "构建失败，线上未受影响"

    # 6. 先迁移再换容器，要求迁移向后兼容（旧代码能跑在新结构上）。
    #    必须用 run 而非 exec：exec 打到的是旧容器，里面是旧镜像的
    #    alembic 脚本，本次新增的迁移根本不存在。run 会从刚构建的
    #    新镜像起一个临时容器，拿到的才是完整迁移链。
    if ! run_fg "数据库迁移" dc run --rm --no-deps admin-api alembic upgrade head; then
        err "迁移失败。旧容器仍在运行，可执行回滚：bash deploy/deploy.sh rollback"
    fi

    # 7. 逐个替换应用层容器，数据层不动
    section "滚动重启应用层"
    for svc in admin-api gateway-api worker dashboard-ui; do
        run_step "更新 $svc" dc up -d --no-deps --force-recreate "$svc" \
            || err "$svc 更新失败，执行回滚：bash deploy/deploy.sh rollback"
    done

    # 8. 验收
    section "更新后验收"
    local verify_status=0
    verify_endpoints || verify_status=1

    echo ""
    dc ps

    if [ "$verify_status" -ne 0 ]; then
        echo ""
        echo -e "${RED}验收未通过${NC}"
        echo "  回滚：bash deploy/deploy.sh rollback"
        exit 1
    fi

    run_step "清理悬空镜像" docker image prune -f || true

    echo ""
    echo -e "${GREEN}════════ 更新完成 ${old_tag} → ${new_tag} ════════${NC}"
    echo "  回滚：bash deploy/deploy.sh rollback"
}

# ──────────────────── status ────────────────────

cmd_status() {
    cd "$PROJECT_DIR"
    require_env_file

    local ui gw
    ui="$(ui_port)"; gw="$(gateway_port)"

    echo -e "${BLUE}══ 部署信息 ══${NC}"
    echo "  版本      $(read_env IMAGE_TAG unknown)"
    echo "  提交      $(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    if [ -f "$SCRIPT_DIR/.deploy-state/current.env" ]; then
        echo "  部署时间  $(grep -oP '^DEPLOY_TIME=\K.*' "$SCRIPT_DIR/.deploy-state/current.env" 2>/dev/null || echo unknown)"
    fi

    echo ""
    echo -e "${BLUE}══ 容器状态 ══${NC}"
    dc ps 2>/dev/null || echo "  容器未运行"

    echo ""
    echo -e "${BLUE}══ 健康检查 ══${NC}"
    local checks=(
        "gateway-api|http://127.0.0.1:${gw}/v2/healthz"
        "gateway ready|http://127.0.0.1:${gw}/v2/readyz"
        "dashboard-ui|http://127.0.0.1:${ui}/healthz"
        "admin-api|http://127.0.0.1:${ui}/api/v2/healthz"
    )
    for item in "${checks[@]}"; do
        local name="${item%%|*}" url="${item#*|}"
        if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
            printf "  %-16s ${GREEN}正常${NC}\n" "$name"
        else
            printf "  %-16s ${RED}异常${NC}\n" "$name"
        fi
    done

    if dc exec -T worker curl -fsS --max-time 5 http://127.0.0.1:9091/healthz >/dev/null 2>&1; then
        printf "  %-16s ${GREEN}正常${NC}\n" "worker"
    else
        printf "  %-16s ${RED}异常${NC}\n" "worker"
    fi

    echo ""
    echo -e "${BLUE}══ 资源占用 ══${NC}"
    docker stats --no-stream \
        --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
        $(dc ps -q 2>/dev/null) 2>/dev/null || echo "  无法获取"

    echo ""
    echo -e "${BLUE}══ 磁盘占用 ══${NC}"
    docker system df 2>/dev/null | sed 's/^/  /' || true

    # 重启次数是隐性故障的信号：容器反复崩但 restart:always 让它看起来在跑
    echo ""
    echo -e "${BLUE}══ 重启次数 ══${NC}"
    for c in fangyu-gateway fangyu-admin fangyu-worker fangyu-ui; do
        local rc
        rc="$(docker inspect -f '{{.RestartCount}}' "$c" 2>/dev/null || echo -)"
        if [ "$rc" = "0" ]; then
            printf "  %-18s %s\n" "$c" "$rc"
        else
            printf "  %-18s ${YELLOW}%s${NC}\n" "$c" "$rc"
        fi
    done
}

# ──────────────────── logs ────────────────────

cmd_logs() {
    cd "$PROJECT_DIR"
    require_env_file
    local svc="${1:-}" lines="${2:-100}"

    # 第一个参数是纯数字时视为行数，兼容 `logs 200` 写法
    if [[ "$svc" =~ ^[0-9]+$ ]]; then
        lines="$svc"; svc=""
    fi

    if [ -n "$svc" ]; then
        dc logs -f --tail "$lines" "$svc"
    else
        dc logs -f --tail "$lines"
    fi
}

# ──────────────────── restart / stop / start ────────────────────

cmd_restart() {
    section "重启服务"
    cd "$PROJECT_DIR"
    require_env_file
    local svc="${1:-}"

    if [ -n "$svc" ]; then
        run_step "重启 $svc" dc restart "$svc" || err "重启 $svc 失败"
    else
        # 只重启应用层，数据层重启会中断所有连接且无必要
        for s in admin-api gateway-api worker dashboard-ui; do
            run_step "重启 $s" dc restart "$s" || warn "$s 重启失败"
        done
    fi

    section "验收"
    verify_endpoints || { warn "验收未通过，查看日志：bash deploy/deploy.sh logs"; exit 1; }
    log "重启完成"
}

cmd_stop() {
    section "停止服务"
    cd "$PROJECT_DIR"
    require_env_file
    # 用 stop 而非 down：保留容器与网络，下次 start 更快，且不碰数据卷
    run_step "停止全部容器" dc stop || err "停止失败"
    log "服务已停止（数据卷保留）"
}

cmd_start() {
    section "启动服务"
    cd "$PROJECT_DIR"
    require_env_file
    run_step "启动数据层" dc up -d redis mysql clickhouse || err "数据层启动失败"
    wait_data_layer || err "数据层未就绪"
    run_step "启动应用层" dc up -d || err "应用层启动失败"
    section "验收"
    verify_endpoints || { warn "验收未通过"; exit 1; }
    log "服务已启动"
}

cmd_down() {
    cd "$PROJECT_DIR"
    require_env_file
    echo -e "${YELLOW}将删除所有容器与网络（数据卷保留）${NC}"
    if [ -t 0 ] && [ "${NON_INTERACTIVE:-0}" != "1" ]; then
        read -rp "  确认？(yes/no): " confirm
        [ "$confirm" = "yes" ] || { log "已取消"; return 0; }
    fi
    run_step "销毁容器与网络" dc down --remove-orphans || err "操作失败"
    log "已销毁。数据卷仍在，docker volume ls 可查看"
}

# ──────────────────── doctor ────────────────────

# 部署失败后的定向诊断，覆盖本项目最常踩的几个坑
cmd_doctor() {
    cd "$PROJECT_DIR"
    require_env_file

    section "故障诊断"

    echo -e "${BLUE}── 退出的容器 ──${NC}"
    local dead
    dead="$(dc ps -a --status exited --format '{{.Name}}' 2>/dev/null || true)"
    if [ -n "$dead" ]; then
        echo "$dead" | sed 's/^/  /'
        echo ""
        for c in $dead; do
            echo -e "${YELLOW}  ── $c 最后 30 行 ──${NC}"
            docker logs --tail 30 "$c" 2>&1 | sed 's/^/  │  /' || true
            echo ""
        done
    else
        echo "  无"
    fi

    echo -e "${BLUE}── 配置校验 ──${NC}"

    # CORS 格式：本项目最高频的启动崩溃原因
    for key in ADMIN_CORS_ORIGINS GATEWAY_CORS_ORIGINS; do
        local val
        val="$(read_env "$key")"
        if [[ "$val" == \[*\] ]]; then
            echo -e "  ${GREEN}✓${NC} $key 为 JSON 数组"
        else
            echo -e "  ${RED}✗${NC} $key 不是 JSON 数组，服务会启动即崩：$val"
        fi
    done

    # 连接串主机名
    for key in ADMIN_DATABASE_URL ADMIN_REDIS_URL GATEWAY_REDIS_URL WORKER_REDIS_URL; do
        local val
        val="$(read_env "$key")"
        if [[ "$val" == *localhost* || "$val" == *127.0.0.1* ]]; then
            echo -e "  ${RED}✗${NC} $key 指向 localhost，容器内应用服务名"
        else
            echo -e "  ${GREEN}✓${NC} $key 主机名正常"
        fi
    done

    echo ""
    echo -e "${BLUE}── 内部连通性 ──${NC}"

    # 用 curl 探 TCP 可达性（镜像内确定有 curl，healthcheck 依赖它）。
    # 连不上返回 7，能连上但协议不匹配返回 52/56 —— 后两者也算网络通。
    #
    # --max-time 必须给：telnet:// 模式下 curl 建连后会一直等对端数据且不自行
    # 断开，MySQL 发完握手包也不会关连接，仅有 --connect-timeout 会永久悬挂。
    # 超时返回 28，与 7 区分即可判定网络通。
    if dc ps -q admin-api >/dev/null 2>&1 && [ -n "$(dc ps -q admin-api 2>/dev/null)" ]; then
        for target in "mysql:3306" "redis:6379" "clickhouse:8123"; do
            local code=0
            dc exec -T admin-api \
                curl -s --connect-timeout 3 --max-time 5 "telnet://${target}" \
                >/dev/null 2>&1 || code=$?
            if [ "$code" = "7" ]; then
                echo -e "  ${RED}✗${NC} admin-api → $target 不通（连接被拒绝）"
            else
                echo -e "  ${GREEN}✓${NC} admin-api → $target 可达"
            fi
        done
    else
        echo "  admin-api 容器未运行，跳过"
    fi

    echo ""
    echo -e "${BLUE}── 事件链路 ──${NC}"

    # gateway 写入与 worker 消费的 Stream 名必须一致，否则决策日志永远为空
    local gw_stream wk_stream
    gw_stream="$(dc exec -T gateway-api printenv GATEWAY_EVENT_STREAM_NAME 2>/dev/null | tr -d '\r' || echo '')"
    wk_stream="$(dc exec -T worker printenv WORKER_STREAM_NAME 2>/dev/null | tr -d '\r' || echo '')"
    if [ -n "$gw_stream" ] && [ "$gw_stream" = "$wk_stream" ]; then
        echo -e "  ${GREEN}✓${NC} Stream 名一致：$gw_stream"
    else
        echo -e "  ${RED}✗${NC} Stream 名不一致 gateway='$gw_stream' worker='$wk_stream'"
    fi

    # ClickHouse 库名必须是 fangyu，SQL 里表前缀硬编码
    local ch_db
    ch_db="$(dc exec -T worker printenv WORKER_CLICKHOUSE_DATABASE 2>/dev/null | tr -d '\r' || echo '')"
    if [ "$ch_db" = "fangyu" ]; then
        echo -e "  ${GREEN}✓${NC} ClickHouse 库名 fangyu"
    else
        echo -e "  ${RED}✗${NC} ClickHouse 库名为 '$ch_db'，必须是 fangyu（SQL 中表前缀硬编码）"
    fi

    echo ""
    echo -e "${BLUE}── 磁盘与端口 ──${NC}"
    df -h / /var/lib/docker 2>/dev/null | sed 's/^/  /' || true
    echo ""
    ss -tlnp 2>/dev/null | grep -E ':(80|443|8000|8080|3306|6379|8123)\b' | sed 's/^/  /' || true

    echo ""
    echo "  完整日志目录：$LOG_DIR"
}

# ──────────────────── 委派给 scripts/ ────────────────────

cmd_verify() {
    cd "$PROJECT_DIR"
    require_env_file
    bash "$SCRIPTS_DIR/smoke-test.sh"
}

cmd_backup() {
    cd "$PROJECT_DIR"
    require_env_file
    bash "$SCRIPTS_DIR/backup.sh"
}

cmd_rollback() {
    cd "$PROJECT_DIR"
    require_env_file
    bash "$SCRIPTS_DIR/rollback.sh" "$@"
}

cmd_preflight() {
    cd "$PROJECT_DIR"
    bash "$SCRIPTS_DIR/preflight.sh"
}

cmd_ssl() {
    [ $# -gt 0 ] || err "用法：bash deploy/deploy.sh ssl <域名> [域名...]"
    bash "$SCRIPTS_DIR/check-ssl.sh" "$@"
}

cmd_shell() {
    cd "$PROJECT_DIR"
    require_env_file
    local svc="${1:-admin-api}"
    dc exec "$svc" sh
}

# ──────────────────── 入口 ────────────────────

print_usage() {
    cat <<'USAGE'
Evercookie Defense System V2 — 部署与运维入口

用法：bash deploy/deploy.sh <命令> [参数]

部署：
  clone [目录] [仓库]   克隆代码并自动转入 init
  init                  首次部署：生成配置 → 预检 → 构建 → 启动 → 迁移 → 验收
  update                更新部署：拉代码 → 备份 → 构建 → 迁移 → 滚动重启 → 验收
  rollback [版本]       回滚到上一版或指定版本

运维：
  status                部署信息、容器状态、健康检查、资源与重启次数
  logs [服务] [行数]    跟踪日志，不带服务名则全部
  restart [服务]        重启，不带服务名则重启应用层
  start                 启动全部服务
  stop                  停止全部容器（保留数据卷）
  down                  销毁容器与网络（保留数据卷，需确认）
  shell [服务]          进入容器 shell，默认 admin-api

检查：
  preflight             部署前环境检查
  verify                部署后端到端冒烟测试
  doctor                故障诊断，定位常见配置错误
  ssl <域名>...         证书有效期与协议校验
  backup                全量备份

环境变量：
  GIT_REPO              clone 的仓库地址
  GIT_BRANCH            分支，默认 main
  ENV_FILE              环境变量文件，默认 .env.production
  SKIP_BACKUP=1         update 时跳过备份
  NON_INTERACTIVE=1     跳过所有交互提示
  NO_ANIMATION=1        关闭进度动画
  DISK_MIN_GB           预检磁盘门槛，默认 50（放宽有数据丢失风险）

示例：
  # 服务器上从零开始
  export GIT_REPO=https://github.com/your-org/evercookie-system.git
  bash deploy/deploy.sh clone /opt/fangyu

  # 已有代码
  cd /opt/fangyu && bash deploy/deploy.sh init

  # 发新版本
  sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=v2.0.1/' .env.production
  bash deploy/deploy.sh update

  # 出问题
  bash deploy/deploy.sh doctor
  bash deploy/deploy.sh rollback

注意：容器只监听 127.0.0.1，公网访问需在 1Panel OpenResty 配置反代。
      模板见 deploy/openresty/，完整说明见 deploy/README.md
USAGE
}

main() {
    local cmd="${1:-}"
    [ $# -gt 0 ] && shift || true

    case "$cmd" in
        clone)      cmd_clone "$@" ;;
        init)       cmd_init ;;
        update)     cmd_update ;;
        rollback)   cmd_rollback "$@" ;;
        status)     cmd_status ;;
        logs)       cmd_logs "$@" ;;
        restart)    cmd_restart "$@" ;;
        start)      cmd_start ;;
        stop)       cmd_stop ;;
        down)       cmd_down ;;
        shell)      cmd_shell "$@" ;;
        preflight)  cmd_preflight ;;
        verify)     cmd_verify ;;
        doctor)     cmd_doctor ;;
        ssl)        cmd_ssl "$@" ;;
        backup)     cmd_backup ;;
        -h|--help|help|"") print_usage ;;
        *)
            echo -e "${RED}未知命令: $cmd${NC}" >&2
            echo ""
            print_usage
            exit 1
            ;;
    esac
}

main "$@"
