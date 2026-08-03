#!/usr/bin/env bash
# =============================================================================
# 回滚到上一版本镜像
# -----------------------------------------------------------------------------
# 用法：
#   bash deploy/scripts/rollback.sh              # 回滚到 .deploy-state 记录的上一版
#   bash deploy/scripts/rollback.sh v2.0.1       # 回滚到指定 tag
#
# 重要：本脚本只回滚镜像，不回滚数据库。
# 若本次部署包含破坏性迁移（删列/改类型），必须先用 backup.sh 的
# 备份文件恢复数据库，再执行镜像回滚。alembic downgrade 对
# 已丢数据的列无能为力。
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env.production}"
COMPOSE="$REPO_ROOT/deploy/docker-compose.prod.yml"
STATE_DIR="$REPO_ROOT/deploy/.deploy-state"

step() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '  %s\n' "$*"; }

[[ -f "$ENV_FILE" ]] || die "缺少 $ENV_FILE"

# ── 确定目标版本 ──────────────────────────────────────────────
TARGET_TAG="${1:-}"
if [[ -z "$TARGET_TAG" ]]; then
    [[ -f "$STATE_DIR/previous.env" ]] \
        || die "无历史版本记录。请显式指定 tag：bash $0 <tag>"
    TARGET_TAG="$(grep -oP '^IMAGE_TAG=\K.*' "$STATE_DIR/previous.env")"
    [[ -n "$TARGET_TAG" ]] || die "历史记录中未找到 IMAGE_TAG"
fi

CURRENT_TAG="$(grep -oP '^IMAGE_TAG=\K.*' "$ENV_FILE")"
REGISTRY="$(grep -oP '^IMAGE_REGISTRY=\K.*' "$ENV_FILE" || echo fangyu)"

step "回滚计划"
info "当前版本：$CURRENT_TAG"
info "目标版本：$TARGET_TAG"

[[ "$CURRENT_TAG" == "$TARGET_TAG" ]] && die "目标版本与当前版本相同，无需回滚"

# ── 校验目标镜像存在 ──────────────────────────────────────────
step "校验目标镜像"
MISSING=0
for svc in gateway-api admin-api worker dashboard-ui; do
    if docker image inspect "${REGISTRY}/${svc}:${TARGET_TAG}" >/dev/null 2>&1; then
        info "${REGISTRY}/${svc}:${TARGET_TAG} 存在"
    else
        printf '\033[31m  ✗ 缺少镜像 %s/%s:%s\033[0m\n' "$REGISTRY" "$svc" "$TARGET_TAG"
        MISSING=1
    fi
done
[[ "$MISSING" == "0" ]] || die "目标镜像不完整，无法回滚。可用镜像：
$(docker images "${REGISTRY}/*" --format '  {{.Repository}}:{{.Tag}}')"

# ── 执行回滚 ──────────────────────────────────────────────────
step "切换镜像版本"

# 只改 IMAGE_TAG 一行，其余配置保持不动。
# 先备份 env 文件，避免 sed 出错后无法恢复。
cp "$ENV_FILE" "$ENV_FILE.rollback-bak"
sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${TARGET_TAG}|" "$ENV_FILE"
info "IMAGE_TAG 已改为 $TARGET_TAG"

dc() { docker compose -f "$COMPOSE" --env-file "$ENV_FILE" "$@"; }

# 只重建应用层，数据层容器不动——避免无谓的数据库重启
if ! dc up -d --no-build gateway-api admin-api worker dashboard-ui; then
    printf '\033[31m回滚启动失败，恢复 env 文件\033[0m\n'
    mv "$ENV_FILE.rollback-bak" "$ENV_FILE"
    die "回滚失败，配置已恢复。请人工介入排查"
fi

rm -f "$ENV_FILE.rollback-bak"

# ── 健康校验 ──────────────────────────────────────────────────
step "健康校验"

UI_PORT="$(grep -oP '^UI_PUBLISH_PORT=\K.*'      "$ENV_FILE" || echo 8080)"
GW_PORT="$(grep -oP '^GATEWAY_PUBLISH_PORT=\K.*' "$ENV_FILE" || echo 8000)"

FAIL=0
for probe in "http://127.0.0.1:${GW_PORT}/v2/healthz|gateway-api" \
             "http://127.0.0.1:${UI_PORT}/healthz|dashboard-ui" \
             "http://127.0.0.1:${UI_PORT}/api/v2/healthz|admin-api"; do
    url="${probe%%|*}"; name="${probe##*|}"
    OK=0
    for _ in $(seq 1 30); do
        curl -fsS --max-time 5 "$url" >/dev/null 2>&1 && { OK=1; break; }
        sleep 2
    done
    if [[ "$OK" == "1" ]]; then
        info "$name 就绪"
    else
        printf '\033[31m  ✗ %s 探活失败\033[0m\n' "$name"
        FAIL=1
    fi
done

# ── 更新状态记录 ──────────────────────────────────────────────
mkdir -p "$STATE_DIR"
{
    echo "IMAGE_TAG=$TARGET_TAG"
    echo "ROLLED_BACK_FROM=$CURRENT_TAG"
    echo "DEPLOY_TIME=$(date -Iseconds)"
} > "$STATE_DIR/current.env"

printf '\n'
dc ps

if [[ "$FAIL" != "0" ]]; then
    die "回滚后健康校验未通过，需人工介入：docker compose -f $COMPOSE logs --tail=100"
fi

printf '\n\033[32m✓ 已回滚到 %s\033[0m\n' "$TARGET_TAG"
printf '\n注意：数据库结构未回滚。如本次发布含破坏性迁移，\n'
printf '需从 deploy/backups/ 恢复对应时间点的 MySQL 备份。\n'
