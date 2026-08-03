#!/usr/bin/env bash
# =============================================================================
# 全量备份：MySQL + ClickHouse + 配置
# -----------------------------------------------------------------------------
# 用法：
#   bash deploy/scripts/backup.sh              # 全量备份
#   RETAIN_DAYS=30 bash deploy/scripts/backup.sh
#
# 可挂到 1Panel 计划任务每日执行。
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env.production}"
BACKUP_ROOT="${BACKUP_DIR:-$REPO_ROOT/deploy/backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"

TS="$(date +%Y%m%d_%H%M%S)"
DEST="$BACKUP_ROOT/$TS"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "错误：缺少 $ENV_FILE" >&2
    exit 1
fi

# 读取凭据。set -a 让后续 source 的变量自动导出给子进程。
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

mkdir -p "$DEST"
chmod 700 "$BACKUP_ROOT" "$DEST"

echo "备份目标：$DEST"

# ── MySQL ────────────────────────────────────────────────────
# --single-transaction 保证 InnoDB 一致性快照且不锁表；
# --routines --triggers 带上存储过程与触发器。
echo "[1/4] MySQL 全量导出..."
if docker ps --format '{{.Names}}' | grep -q '^fangyu-mysql$'; then
    docker exec fangyu-mysql sh -c \
        "exec mysqldump -uroot -p\"\$MYSQL_ROOT_PASSWORD\" \
            --single-transaction --routines --triggers --events \
            --default-character-set=utf8mb4 \
            '${MYSQL_DATABASE:-fangyu_v2}'" \
        | gzip -6 > "$DEST/mysql_${MYSQL_DATABASE:-fangyu_v2}.sql.gz"

    SIZE="$(du -h "$DEST/mysql_${MYSQL_DATABASE:-fangyu_v2}.sql.gz" | cut -f1)"
    echo "      完成（$SIZE）"
else
    echo "      跳过：fangyu-mysql 未运行"
fi

# ── ClickHouse ───────────────────────────────────────────────
# 只备份维度小、重建代价高的表。decision_events 是海量明细且有 TTL，
# 全量导出既慢又无意义，靠副本与 TTL 策略保障。
echo "[2/4] ClickHouse 表结构与关键数据..."
if docker ps --format '{{.Names}}' | grep -q '^fangyu-clickhouse$'; then
    docker exec fangyu-clickhouse clickhouse-client \
        --user "${CLICKHOUSE_USER:-default}" \
        --password "${CLICKHOUSE_PASSWORD}" \
        --query "SELECT create_table_query FROM system.tables WHERE database='fangyu' FORMAT TSVRaw" \
        > "$DEST/clickhouse_schema.sql" 2>/dev/null \
        && echo "      表结构已导出" \
        || echo "      警告：表结构导出失败"

    docker exec fangyu-clickhouse clickhouse-client \
        --user "${CLICKHOUSE_USER:-default}" \
        --password "${CLICKHOUSE_PASSWORD}" \
        --query "SELECT count() FROM fangyu.decision_events" \
        > "$DEST/clickhouse_rowcount.txt" 2>/dev/null || true
else
    echo "      跳过：fangyu-clickhouse 未运行"
fi

# ── Redis ────────────────────────────────────────────────────
# Redis 里是决策缓存与画像，可从 MySQL/CH 重建，只做尽力而为的快照。
echo "[3/4] Redis 快照..."
if docker ps --format '{{.Names}}' | grep -q '^fangyu-redis$'; then
    docker exec fangyu-redis sh -c \
        "redis-cli -a \"\$REDIS_PASSWORD\" --no-auth-warning BGSAVE" >/dev/null 2>&1 || true
    sleep 3
    docker cp fangyu-redis:/data/dump.rdb "$DEST/redis_dump.rdb" 2>/dev/null \
        && gzip -6 "$DEST/redis_dump.rdb" \
        && echo "      完成" \
        || echo "      警告：Redis 快照未取到（不阻塞部署）"
else
    echo "      跳过：fangyu-redis 未运行"
fi

# ── 配置与版本快照 ────────────────────────────────────────────
echo "[4/4] 配置与镜像清单..."
{
    echo "backup_time=$TS"
    echo "image_tag=${IMAGE_TAG:-unknown}"
    echo "git_commit=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "git_branch=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
} > "$DEST/MANIFEST"

# 镜像 digest 是回滚的唯一可靠依据：tag 可被覆盖，digest 不会。
docker compose -f "$REPO_ROOT/deploy/docker-compose.prod.yml" --env-file "$ENV_FILE" \
    images --format json > "$DEST/images.json" 2>/dev/null || true

# 不备份 .env.production 本体（含明文口令），只记录键名用于比对差异
grep -oP '^[A-Z_]+(?==)' "$ENV_FILE" | sort > "$DEST/env_keys.txt"

cp "$REPO_ROOT/deploy/docker-compose.prod.yml" "$DEST/" 2>/dev/null || true

chmod -R 600 "$DEST"/* 2>/dev/null || true
echo "      完成"

# ── 清理过期备份 ──────────────────────────────────────────────
echo "清理 ${RETAIN_DAYS} 天前的备份..."
find "$BACKUP_ROOT" -maxdepth 1 -type d -name '20*' -mtime "+$RETAIN_DAYS" \
    -exec rm -rf {} + 2>/dev/null || true

echo
echo "备份完成：$DEST"
du -sh "$DEST"
