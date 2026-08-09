# 迁移失败快速修复指南

## 问题现象

```
FAILED: Can't locate revision identified by '20260809_0023'
```

## 一键修复（生产服务器执行）

```bash
# SSH 登录生产服务器
ssh root@adminPanel-001

# 进入项目目录
cd /opt/fangyu-defense-system

# 执行修复脚本（自动检查并修复版本号）
bash deploy/scripts/fix_alembic_version.sh

# 重新部署
bash deploy/deploy.sh update
```

## 手动修复（如脚本失败）

```bash
# 1. 检查当前版本
docker exec -it deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} -D fangyu_defense -e "
SELECT * FROM alembic_version;
"

# 2. 修复版本号
docker exec -i deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} fangyu_defense <<EOF
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('20260809_0001');
EOF

# 3. 验证
docker exec -it deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} -D fangyu_defense -e "
SELECT version_num FROM alembic_version;
"

# 4. 重新部署
bash deploy/deploy.sh update
```

## 原因说明

- 本地代码已重构为单一初始化迁移 `20260809_0001`
- 生产数据库记录了旧版本号 `20260809_0023`
- Alembic 无法找到旧版本文件构建升级路径

## 相关文档

- 详细修复方案：[docs/MIGRATION_FIX_20260809.md](../docs/MIGRATION_FIX_20260809.md)
- SQL 检查脚本：[admin-api/alembic/fix_version.sql](../admin-api/alembic/fix_version.sql)
