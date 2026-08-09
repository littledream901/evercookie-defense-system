#!/usr/bin/env bash
# =============================================================================
# 清理 Docker 构建缓存并重新部署
# 用途：解决镜像中包含旧的 Python __pycache__ 导致的迁移失败
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  清理构建缓存并重新部署${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

# 1. 清理本地 Python 缓存
echo -e "${YELLOW}[1/4] 清理本地 Python 缓存...${NC}"
find "$PROJECT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PROJECT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
echo -e "${GREEN}✓${NC} 本地缓存已清理"
echo ""

# 2. 清理 Docker 构建缓存
echo -e "${YELLOW}[2/4] 清理 Docker 构建缓存...${NC}"
docker builder prune -f
echo -e "${GREEN}✓${NC} Docker 构建缓存已清理"
echo ""

# 3. 删除旧镜像
echo -e "${YELLOW}[3/4] 删除旧镜像...${NC}"
OLD_IMAGES=$(docker images --filter "reference=fangyu/*" --format "{{.Repository}}:{{.Tag}}" | grep -v "<none>")
if [ -n "$OLD_IMAGES" ]; then
    echo "$OLD_IMAGES" | while read img; do
        echo "  删除: $img"
        docker rmi "$img" 2>/dev/null || true
    done
    echo -e "${GREEN}✓${NC} 旧镜像已删除"
else
    echo "  无旧镜像需要删除"
fi
echo ""

# 4. 重新部署
echo -e "${YELLOW}[4/4] 重新部署（--no-cache）...${NC}"
echo ""
cd "$PROJECT_DIR"
bash deploy/deploy.sh update

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  完成${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
