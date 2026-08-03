#!/usr/bin/env bash
# =============================================================================
# 生成随机口令并写入 .env.production
# -----------------------------------------------------------------------------
# 只替换 __REPLACE_*__ 占位符，已填写的真实值不会被覆盖，可重复执行。
# 同时自动生成 URL 编码版本，避免密码含特殊字符时连接串解析失败。
#
# 用法：bash deploy/scripts/gen-secrets.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env.production}"
TEMPLATE="$REPO_ROOT/.env.production.example"

if [[ ! -f "$ENV_FILE" ]]; then
    if [[ ! -f "$TEMPLATE" ]]; then
        echo "错误：模板 $TEMPLATE 不存在" >&2
        exit 1
    fi
    cp "$TEMPLATE" "$ENV_FILE"
    echo "已从模板创建 $ENV_FILE"
fi

chmod 600 "$ENV_FILE"

# 只用字母数字：避开 shell 与 URL 的转义陷阱，靠长度换取强度。
# 32 位 base62 约 190 bit 熵，远超实际需要。
#
# 不用 `tr < /dev/urandom | head -c N`：head 读满即退出，tr 收到 SIGPIPE
# 返回非零，在 set -o pipefail 下会让整个脚本中止。
# 改为一次性读取足量随机字节后过滤，全程无管道提前关闭。
rand_alnum() {
    local want="${1:-32}"
    local out=""
    # base64 后过滤掉非字母数字，剩余长度约为原始的 3/4，多取几轮确保够用
    while [ "${#out}" -lt "$want" ]; do
        out+="$(LC_ALL=C head -c $((want * 2)) /dev/urandom | base64 | LC_ALL=C tr -cd 'A-Za-z0-9')"
    done
    printf '%s' "${out:0:want}"
}

# 就地替换占位符。值只含字母数字，无需担心 sed 分隔符冲突。
set_placeholder() {
    local placeholder="$1" value="$2"
    if grep -q "$placeholder" "$ENV_FILE"; then
        sed -i "s|${placeholder}|${value}|g" "$ENV_FILE"
        echo "  已生成 ${placeholder}"
    fi
}

echo "生成随机凭据..."

MYSQL_ROOT_PW="$(rand_alnum 32)"
MYSQL_PW="$(rand_alnum 32)"
REDIS_PW="$(rand_alnum 32)"
CH_PW="$(rand_alnum 32)"
JWT="$(rand_alnum 64)"

set_placeholder '__REPLACE_MYSQL_ROOT_PASSWORD__'  "$MYSQL_ROOT_PW"
set_placeholder '__REPLACE_CLICKHOUSE_PASSWORD__'  "$CH_PW"
set_placeholder '__REPLACE_JWT_SECRET_64_CHARS__'  "$JWT"

# MySQL / Redis 口令在两处出现：明文变量与连接串。
# 因取值为纯字母数字，URL 编码后与原文相同，可直接复用同一值。
set_placeholder '__REPLACE_MYSQL_PASSWORD_URLENCODED__' "$MYSQL_PW"
set_placeholder '__REPLACE_MYSQL_PASSWORD__'            "$MYSQL_PW"
set_placeholder '__REPLACE_REDIS_PASSWORD_URLENCODED__' "$REDIS_PW"
set_placeholder '__REPLACE_REDIS_PASSWORD__'            "$REDIS_PW"

echo
if grep -q '__REPLACE_' "$ENV_FILE"; then
    echo "仍有占位符需手工填写："
    grep -o '__REPLACE_[A-Z_]*__' "$ENV_FILE" | sort -u | sed 's/^/  /'
else
    echo "所有凭据占位符已填充。"
fi

echo
echo "仍需手工确认的项："
echo "  ADMIN_CORS_ORIGINS    改为实际后台域名（JSON 数组）"
echo "  GATEWAY_CORS_ORIGINS  改为接入 SDK 的业务域名（JSON 数组）"
echo "  IMAGE_TAG             改为本次发布版本号，勿用 latest"
echo
echo "口令已写入 $ENV_FILE（权限 600）。请立即备份到密码管理器——"
echo "MySQL 数据卷初始化后再改口令需要手工执行 ALTER USER。"
