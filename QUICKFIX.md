## Alembic 迁移失败修复 - 操作清单

**问题**：`Can't locate revision identified by '20260809_0023'`

**根因**：代码重构为单一迁移，但生产数据库记录旧版本号，版本链断裂

---

### ✅ 立即执行（生产服务器）

```bash
# 登录生产服务器
ssh root@adminPanel-001

# 执行修复
cd /opt/fangyu-defense-system
bash deploy/scripts/fix_alembic_version.sh

# 重新部署
bash deploy/deploy.sh update
```

---

### 📋 修复脚本功能

自动执行以下操作：
1. ✅ 检查 MySQL 容器状态
2. ✅ 检查当前 Alembic 版本号
3. ✅ 检查数据库表结构完整性（表数量 ≥ 20）
4. ✅ 检查关键业务表存在性
5. ✅ 交互式确认（可随时取消）
6. ✅ 删除旧版本号并插入新版本号 `20260809_0001`
7. ✅ 验证修复结果

**安全保障**：
- 仅修改 `alembic_version` 表
- 不影响任何业务数据
- 可随时取消操作

---

### 🔧 手动修复（如脚本失败）

```bash
# 1. 检查当前版本
docker exec -it deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} \
  -D fangyu_defense -e "SELECT * FROM alembic_version;"

# 2. 修复版本号
docker exec -i deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} \
  fangyu_defense <<EOF
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('20260809_0001');
EOF

# 3. 验证
docker exec -it deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} \
  -D fangyu_defense -e "SELECT version_num FROM alembic_version;"

# 4. 重新部署
bash deploy/deploy.sh update
```

---

### ✓ 验证步骤

```bash
# 检查迁移版本
docker compose -f deploy/docker-compose.prod.yml exec admin-api alembic current

# 验证服务
bash deploy/deploy.sh verify

# 查看日志
bash deploy/deploy.sh logs admin-api
```

---

### 📁 本次创建的文件

| 文件 | 说明 |
|------|------|
| `deploy/scripts/fix_alembic_version.sh` | 自动修复脚本（含安全检查） |
| `deploy/scripts/README_FIX_MIGRATION.md` | 快速参考 |
| `admin-api/alembic/fix_version.sql` | SQL 检查语句 |
| `docs/MIGRATION_FIX_20260809.md` | 详细修复方案文档 |
| `README_MIGRATION_FIX.md` | 修复方案总览 |

---

### 🔄 回滚选项

如修复后仍有问题：

```bash
bash deploy/deploy.sh rollback
```

备份位置：`/opt/fangyu-defense-system/deploy/backups/20260809_082715`
