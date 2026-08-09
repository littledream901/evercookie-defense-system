#!/usr/bin/env bash
# =============================================================================
# Alembic 版本诊断脚本
# 用途：详细检查数据库中的 alembic_version 表状态
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.production}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 加载环境变量
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

DB_NAME="${MYSQL_DATABASE:-fangyu_v2}"
MYSQL_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'mysql|mariadb' | head -n1)

if [ -z "$MYSQL_CONTAINER" ]; then
    echo -e "${RED}[ERROR]${NC} 未找到运行中的 MySQL 容器"
    exit 1
fi

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Alembic 版本诊断${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}容器信息：${NC}"
echo "  MySQL 容器: $MYSQL_CONTAINER"
echo "  数据库名: $DB_NAME"
echo ""

echo -e "${YELLOW}1. 检查 alembic_version 表是否存在：${NC}"
docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D "$DB_NAME" -e "
    SELECT COUNT(*) AS 'alembic_version表数量' 
    FROM information_schema.tables 
    WHERE table_schema = '$DB_NAME' AND table_name = 'alembic_version';
" 2>/dev/null
echo ""

echo -e "${YELLOW}2. 查看 alembic_version 表结构：${NC}"
docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D "$DB_NAME" -e "DESCRIBE alembic_version;" 2>/dev/null || echo "  表不存在或无法访问"
echo ""

echo -e "${YELLOW}3. 查看所有版本记录（包括行数）：${NC}"
docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D "$DB_NAME" -e "
    SELECT COUNT(*) AS '版本记录数' FROM alembic_version;
    SELECT * FROM alembic_version;
" 2>/dev/null || echo "  无法查询"
echo ""

echo -e "${YELLOW}4. 查看数据库中所有表：${NC}"
docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D "$DB_NAME" -e "SHOW TABLES;" 2>/dev/null | head -20
echo ""

echo -e "${YELLOW}5. 本地迁移文件列表：${NC}"
ls -lh "$PROJECT_DIR/admin-api/alembic/versions/"*.py 2>/dev/null || echo "  无迁移文件"
echo ""

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
