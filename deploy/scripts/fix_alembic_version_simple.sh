#!/usr/bin/env bash
# =============================================================================
# Alembic 版本号快速修复脚本（简化版）
# 直接修复版本号，跳过复杂检查
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

TARGET_VERSION="20260809_0001"

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Alembic 版本号快速修复${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

# 自动检测 MySQL 容器
MYSQL_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'mysql|mariadb' | head -n1)

if [ -z "$MYSQL_CONTAINER" ]; then
    echo -e "${RED}[ERROR]${NC} 未找到运行中的 MySQL 容器"
    echo ""
    echo "请先启动 MySQL："
    echo -e "  ${CYAN}docker compose -f deploy/docker-compose.prod.yml up -d mysql${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} MySQL 容器: $MYSQL_CONTAINER"
echo ""

# 显示当前版本
echo -e "${YELLOW}当前版本信息：${NC}"
docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D fangyu_defense -e "SELECT * FROM alembic_version;" 2>/dev/null || echo "  无版本记录"
echo ""

# 确认操作
echo -e "${YELLOW}即将执行：${NC}"
echo "  1. 删除所有旧版本记录"
echo "  2. 插入新版本: $TARGET_VERSION"
echo ""
read -p "确认执行？(y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}已取消${NC}"
    exit 0
fi

# 执行修复
echo ""
echo -e "${CYAN}执行修复...${NC}"

docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D fangyu_defense <<EOF
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('$TARGET_VERSION');
SELECT version_num AS '修复后版本' FROM alembic_version;
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  ✓ 修复完成${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "下一步："
    echo -e "  ${CYAN}bash deploy/deploy.sh update${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}修复失败，请检查错误信息${NC}"
    exit 1
fi
