#!/usr/bin/env bash
# Alembic 迁移版本修复脚本
# 用途：修正生产数据库 alembic_version 表，适配合并后的迁移链
# 作者：AI Assistant
# 日期：2026-08-09

set -euo pipefail

# ==================== 配置区 ====================
# 数据库连接信息（从环境变量读取，避免硬编码）
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-fangyu_defense}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-}"

# 目标版本号（合并后的初始迁移）
TARGET_VERSION="20260809_0001"

# ==================== 函数定义 ====================
log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $*"
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $*" >&2
}

check_mysql_client() {
    if ! command -v mysql &> /dev/null; then
        log_error "未找到 mysql 客户端，请先安装 mysql-client"
        exit 1
    fi
}

get_current_version() {
    mysql -h"${DB_HOST}" -P"${DB_PORT}" -u"${DB_USER}" -p"${DB_PASSWORD}" \
        -D"${DB_NAME}" -sN -e "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null || echo ""
}

update_version() {
    local new_version="$1"
    log_info "更新 alembic_version 表到版本: ${new_version}"
    
    mysql -h"${DB_HOST}" -P"${DB_PORT}" -u"${DB_USER}" -p"${DB_PASSWORD}" \
        -D"${DB_NAME}" <<EOF
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('${new_version}');
EOF
    
    if [ $? -eq 0 ]; then
        log_info "版本号更新成功"
        return 0
    else
        log_error "版本号更新失败"
        return 1
    fi
}

# ==================== 主流程 ====================
main() {
    log_info "===== Alembic 迁移版本修复脚本 ====="
    
    # 1. 检查 mysql 客户端
    check_mysql_client
    
    # 2. 获取当前版本
    log_info "检查当前 alembic_version..."
    current_version=$(get_current_version)
    
    if [ -z "${current_version}" ]; then
        log_error "无法读取当前版本号，请检查数据库连接配置"
        exit 1
    fi
    
    log_info "当前版本: ${current_version}"
    
    # 3. 检查是否需要修复
    if [ "${current_version}" = "${TARGET_VERSION}" ]; then
        log_info "当前版本已是目标版本 ${TARGET_VERSION}，无需修复"
        exit 0
    fi
    
    # 4. 执行版本修正
    log_info "开始修正版本号..."
    if update_version "${TARGET_VERSION}"; then
        log_info "✅ 版本修正完成: ${current_version} → ${TARGET_VERSION}"
        log_info "下一步请执行: alembic stamp head"
    else
        log_error "❌ 版本修正失败，请检查日志"
        exit 1
    fi
}

# ==================== 入口 ====================
# 检查必需的环境变量
if [ -z "${DB_PASSWORD}" ]; then
    log_error "环境变量 DB_PASSWORD 未设置，请先配置数据库密码"
    log_info "示例: export DB_PASSWORD='your_password'"
    exit 1
fi

main "$@"
