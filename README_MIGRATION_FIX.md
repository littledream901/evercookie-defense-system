# Alembic 迁移失败修复方案总览

## 📋 问题描述

部署 v2.0.4 版本时，数据库迁移失败并报错：

```
FAILED: Can't locate revision identified by '20260809_0023'
ERROR [alembic.util.messaging] Can't locate revision identified by '20260809_0023'
```

## 🔍 根本原因

1. **迁移文件重构**：本地代码已合并为单一初始化迁移 `20260809_0001_initial_complete_schema.py`
2. **版本链断裂**：生产数据库 `alembic_version` 表记录了旧版本号（如 `20260809_0023`）
3. **Alembic 查找失败**：无法找到旧版本迁移文件，导致无法构建从当前版本到 `head` 的升级路径

## ⚡ 快速修复（推荐）

### 在生产服务器执行：

```bash
# 1. SSH 登录生产服务器
ssh root@adminPanel-001

# 2. 进入项目目录
cd /opt/fangyu-defense-system

# 3. 执行自动修复脚本
bash deploy/scripts/fix_alembic_version.sh

# 4. 重新部署
bash deploy/deploy.sh update
```

**说明**：修复脚本会自动检查数据库表结构完整性，安全更新版本号，无数据丢失风险。

## 🛠️ 手动修复（备选）

如果自动脚本失败或需要手动控制，可按以下步骤操作：

### 步骤 1：检查当前状态

```bash
docker exec -it deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} -D fangyu_defense -e "
SELECT version_num AS '当前版本' FROM alembic_version;
SHOW TABLES;
"
```

### 步骤 2：修复版本号

```bash
docker exec -i deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} fangyu_defense <<EOF
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('20260809_0001');
SELECT version_num AS '修复后版本' FROM alembic_version;
EOF
```

### 步骤 3：验证并重新部署

```bash
# 验证版本号
docker exec -it deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} -D fangyu_defense -e "
SELECT version_num FROM alembic_version;
"

# 重新部署
cd /opt/fangyu-defense-system
bash deploy/deploy.sh update
```

## 📁 相关文件

| 文件 | 说明 |
|------|------|
| [deploy/scripts/fix_alembic_version.sh](deploy/scripts/fix_alembic_version.sh) | 自动修复脚本（含安全检查） |
| [deploy/scripts/README_FIX_MIGRATION.md](deploy/scripts/README_FIX_MIGRATION.md) | 快速参考指南 |
| [admin-api/alembic/fix_version.sql](admin-api/alembic/fix_version.sql) | SQL 检查与修复语句 |
| [admin-api/alembic/versions/20260809_0001_initial_complete_schema.py](admin-api/alembic/versions/20260809_0001_initial_complete_schema.py) | 当前唯一迁移文件 |

## ✅ 验证步骤

修复完成后，执行以下验证：

```bash
# 1. 检查迁移版本
docker compose -f deploy/docker-compose.prod.yml exec admin-api alembic current
# 应显示：20260809_0001 (head)

# 2. 验证服务健康状态
bash deploy/deploy.sh verify

# 3. 检查服务日志
bash deploy/deploy.sh logs admin-api
```

## 🔒 安全性说明

- ✅ 修复操作仅更新 `alembic_version` 表的版本号
- ✅ 不会修改任何业务数据
- ✅ 不会删除或修改表结构
- ✅ 修复脚本包含表结构完整性检查
- ✅ 支持交互式确认，可随时取消

## 🚨 注意事项

1. **数据库结构必须完整**：确保生产数据库已包含所有必需的表和字段
2. **仅修复版本号不匹配**：如果表结构确实缺失，需要执行完整迁移而非仅修复版本号
3. **备份已自动完成**：部署脚本在失败前已完成备份（步骤[2]），位于 `/opt/fangyu-defense-system/deploy/backups/`

## 🔄 回滚操作

如果修复后仍有问题，可回滚到旧版本：

```bash
cd /opt/fangyu-defense-system
bash deploy/deploy.sh rollback
```

## 📚 预防措施

为避免未来出现类似问题：

1. **迁移文件不可删除**：已提交的迁移文件禁止删除或重命名
2. **版本链完整性**：重构迁移时使用 Alembic 的 `squash` 功能保持版本链
3. **部署前验证**：
   ```bash
   cd admin-api
   alembic history --verbose
   alembic upgrade head --sql  # 预览 SQL 而不实际执行
   ```

## 🆘 需要帮助？

如遇到问题或需要进一步协助，请查看：
- 详细技术文档：[docs/MIGRATION_FIX_20260809.md](MIGRATION_FIX_20260809.md)
- 部署文档：[deploy/README.md](../deploy/README.md)
