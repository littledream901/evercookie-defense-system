#!/usr/bin/env bash
# =============================================================================
# Alembic 版本号修复脚本
# 用途：修复 "Can't locate revision identified by 'xxx'" 迁移失败问题
# 使用：bash deploy/scripts/fix_alembic_version.sh
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

log()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# 加载环境变量
if [ ! -f "$ENV_FILE" ]; then
    err "环境配置文件不存在: $ENV_FILE"
fi
set -a
source "$ENV_FILE"
set +a

TARGET_VERSION="20260809_0001"

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Alembic 版本号修复工具${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

# 1. 自动检测 MySQL 容器
log "检查 MySQL 容器状态..."

# 优先使用环境变量指定的容器名
if [ -n "${MYSQL_CONTAINER:-}" ]; then
    if docker ps --format '{{.Names}}' | grep -q "^${MYSQL_CONTAINER}$"; then
        echo -e "  ${GREEN}✓${NC} 使用指定容器: $MYSQL_CONTAINER"
    else
        err "指定的 MySQL 容器未运行: $MYSQL_CONTAINER"
    fi
else
    # 自动检测运行中的 MySQL 容器
    MYSQL_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'mysql|mariadb' | head -n1)
    
    if [ -z "$MYSQL_CONTAINER" ]; then
        err "未找到运行中的 MySQL 容器。请先启动服务：
  docker compose -f deploy/docker-compose.prod.yml up -d mysql
  
或设置环境变量：
  export MYSQL_CONTAINER=<容器名称>"
    fi
    
    echo -e "  ${GREEN}✓${NC} 自动检测到容器: $MYSQL_CONTAINER"
fi
echo ""

# 2. 检查当前版本
log "检查当前 Alembic 版本..."
CURRENT_VERSION=$(docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D fangyu_defense -sN -e "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null || echo "none")

if [ "$CURRENT_VERSION" = "$TARGET_VERSION" ]; then
    echo -e "  ${GREEN}✓${NC} 版本号已经正确: $TARGET_VERSION"
    echo ""
    log "无需修复，退出"
    exit 0
else
    echo -e "  ${YELLOW}⚠${NC} 当前版本: ${CURRENT_VERSION:-未找到版本记录}"
    echo -e "  ${YELLOW}⚠${NC} 目标版本: $TARGET_VERSION"
fi
echo ""

# 3. 检查数据库表结构完整性
log "检查数据库表结构完整性..."
TABLE_COUNT=$(docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D fangyu_defense -sN -e "
    SELECT COUNT(*) FROM information_schema.tables 
    WHERE table_schema = 'fangyu_defense'
" 2>/dev/null || echo "0")

echo -e "  数据库表数量: $TABLE_COUNT"

if [ "$TABLE_COUNT" -eq 0 ]; then
    echo ""
    echo -e "${RED}════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  数据库为空，需要执行初始化迁移而非修复版本号${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}请执行以下操作：${NC}"
    echo ""
    echo "  1. 直接执行部署（会自动运行迁移）："
    echo -e "     ${CYAN}bash deploy/deploy.sh update${NC}"
    echo ""
    echo "  2. 或手动执行迁移："
    echo -e "     ${CYAN}docker compose -f deploy/docker-compose.prod.yml run --rm --no-deps admin-api alembic upgrade head${NC}"
    echo ""
    exit 1
fi

if [ "$TABLE_COUNT" -lt 20 ]; then
    warn "表数量偏少（< 20），可能需要完整迁移而非仅修复版本号"
    echo ""
    read -p "  是否继续修复版本号？(y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "用户取消操作"
        exit 0
    fi
fi
echo -e "  ${GREEN}✓${NC} 表结构检查完成"
echo ""

# 4. 检查关键表
log "检查关键业务表..."
MISSING_TABLES=$(docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D fangyu_defense -sN -e "
    SELECT table_name FROM (
        SELECT 'sys_user' AS table_name
        UNION SELECT 'sys_role'
        UNION SELECT 'biz_tenant'
        UNION SELECT 'biz_site'
        UNION SELECT 'rule_disposition'
        UNION SELECT 'scoring_config'
    ) AS required
    WHERE table_name NOT IN (
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'fangyu_defense'
    )
" 2>/dev/null || echo "")

if [ -n "$MISSING_TABLES" ]; then
    err "缺失关键表: $MISSING_TABLES"
fi
echo -e "  ${GREEN}✓${NC} 关键表完整"
echo ""

# 5. 确认修复操作
echo -e "${YELLOW}即将执行以下操作：${NC}"
echo "  1. 删除旧版本记录: $CURRENT_VERSION"
echo "  2. 插入新版本记录: $TARGET_VERSION"
echo ""
read -p "确认执行？(y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log "用户取消操作"
    exit 0
fi

# 6. 执行修复
log "执行版本号修复..."
docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D fangyu_defense -e "
    DELETE FROM alembic_version;
    INSERT INTO alembic_version (version_num) VALUES ('$TARGET_VERSION');
    SELECT version_num AS '修复后版本' FROM alembic_version;
" 2>/dev/null || err "修复失败"

echo -e "  ${GREEN}✓${NC} 版本号已更新为: $TARGET_VERSION"
echo ""

# 7. 验证修复结果
log "验证修复结果..."
NEW_VERSION=$(docker exec "$MYSQL_CONTAINER" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    -D fangyu_defense -sN -e "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null)

if [ "$NEW_VERSION" = "$TARGET_VERSION" ]; then
    echo -e "  ${GREEN}✓${NC} 验证通过"
else
    err "验证失败: 期望 $TARGET_VERSION，实际 $NEW_VERSION"
fi
echo ""

# 8. 提示后续操作
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  修复完成！${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo ""
log "后续步骤："
echo "  1. 重新执行部署："
echo -e "     ${CYAN}cd /opt/fangyu-defense-system${NC}"
echo -e "     ${CYAN}bash deploy/deploy.sh update${NC}"
echo ""
echo "  2. 验证服务状态："
echo -e "     ${CYAN}bash deploy/deploy.sh verify${NC}"
echo ""
