# 数据库迁移失败修复方案

## 问题描述

部署 v2.0.4 时在数据库迁移步骤失败：

```
FAILED: Can't locate revision identified by '20260809_0023'
```

## 根本原因

1. **版本链断裂**：本地代码已重构为单一初始化迁移 `20260809_0001_initial_complete_schema.py`
2. **生产版本记录**：生产数据库 `alembic_version` 表中记录了旧版本号（如 `20260809_0023`）
3. **Alembic 无法构建升级路径**：找不到从 `20260809_0023` 到 `head` 的迁移文件

## 解决方案（3选1）

### 方案 1：手动同步版本号（推荐，无数据丢失）

**适用场景**：生产数据库结构已经是最新的，只是版本号不匹配

**步骤**：

1. 登录生产服务器 MySQL：
```bash
docker exec -it deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD}
```

2. 检查当前版本：
```sql
USE fangyu_defense;
SELECT * FROM alembic_version;
```

3. 检查数据库结构是否完整（核对关键表）：
```sql
SHOW TABLES;
-- 核对是否存在：sys_user, sys_role, biz_site, rule_*, scoring_config 等
```

4. **如果表结构完整**，手动更新版本号：
```sql
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('20260809_0001');
```

5. 重新部署：
```bash
cd /opt/fangyu-defense-system
bash deploy/deploy.sh update
```

---

### 方案 2：创建桥接迁移（适合表结构有差异）

**适用场景**：生产数据库结构与新代码有差异，需要平滑过渡

**步骤**：

1. 在本地 `admin-api/alembic/versions/` 创建桥接迁移：

```python
# 20260809_0002_bridge_from_legacy.py
"""Bridge migration from legacy versions

Revision ID: 20260809_0002
Revises: 20260809_0001
Create Date: 2026-08-09

"""
from alembic import op
import sqlalchemy as sa

revision = '20260809_0002'
down_revision = '20260809_0001'

def upgrade() -> None:
    # 检查并添加缺失的列/表/索引
    # 例如：
    # op.execute("""
    #     ALTER TABLE biz_site 
    #     ADD COLUMN IF NOT EXISTS new_field VARCHAR(64)
    # """)
    pass

def downgrade() -> None:
    pass
```

2. 在生产服务器手动设置起始版本：
```sql
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('20260809_0001');
```

3. 提交代码并重新部署

---

### 方案 3：全新初始化（开发/测试环境）

**适用场景**：开发环境或可以清空数据的测试环境

**警告**：⚠️ **此操作会删除所有数据，仅适用于非生产环境**

```bash
# 1. 备份数据（如有需要）
docker exec deploy-mysql-1 mysqldump -uroot -p${MYSQL_ROOT_PASSWORD} fangyu_defense > backup.sql

# 2. 删除并重建数据库
docker exec -it deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} -e "
DROP DATABASE IF EXISTS fangyu_defense;
CREATE DATABASE fangyu_defense CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"

# 3. 重新部署
bash deploy/deploy.sh update
```

---

## 快速修复命令（方案1）

如果确认生产数据库结构完整，直接执行：

```bash
# 登录生产服务器
ssh root@adminPanel-001

# 修复版本号
docker exec -i deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} fangyu_defense <<EOF
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('20260809_0001');
SELECT '✓ 版本号已更新为 20260809_0001' AS status;
EOF

# 重新部署
cd /opt/fangyu-defense-system
bash deploy/deploy.sh update
```

---

## 验证步骤

1. 检查迁移是否成功：
```bash
docker compose -f deploy/docker-compose.prod.yml exec admin-api alembic current
# 应显示：20260809_0001 (head)
```

2. 检查服务健康状态：
```bash
bash deploy/deploy.sh verify
```

3. 测试关键功能：
   - 登录管理后台
   - 查看站点列表
   - 检查规则配置

---

## 预防措施

1. **迁移文件管理规范**：
   - 已提交的迁移文件禁止删除或重命名
   - 重构时使用合并迁移（squash），保留版本链完整性

2. **部署前检查**：
```bash
# 本地验证迁移链完整性
cd admin-api
alembic history
alembic upgrade head --sql  # 生成 SQL 预览，不实际执行
```

3. **生产环境迁移监控**：
   - 部署脚本已包含备份步骤（步骤[2]）
   - 失败后可回滚：`bash deploy/deploy.sh rollback`

---

## 相关文件

- 迁移文件：`admin-api/alembic/versions/20260809_0001_initial_complete_schema.py`
- 部署脚本：`deploy/deploy.sh`
- 手动 SQL（备用）：`admin-api/manual_migration_api_key.sql`
