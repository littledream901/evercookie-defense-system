# Alembic 迁移版本修复指南

## 问题背景

**发生时间**：2026-08-09  
**影响范围**：生产环境数据库迁移失败  
**错误信息**：`Can't locate revision identified by '20260809_0023'`

### 根本原因

在 commit `7c5bcb0` 中，我们将 26 个历史 alembic 迁移文件合并为单一的初始 schema：
- **旧迁移链**：`20260731_0001` ~ `20260809_0023`（26 个文件）
- **新迁移链**：`20260809_0001_initial_complete_schema.py`（单一文件）

但生产数据库 `alembic_version` 表仍记录旧版本号 `20260809_0023`，导致 alembic 无法找到对应的迁移文件。

---

## 修复方案（推荐）

### 方案一：使用自动化修复脚本（推荐）

#### 1. 配置环境变量

```bash
export DB_HOST="your_db_host"
export DB_PORT="3306"
export DB_NAME="fangyu_defense"
export DB_USER="root"
export DB_PASSWORD="your_db_password"
```

#### 2. 执行修复脚本

```bash
# 进入项目根目录
cd /opt/fangyu-defense-system

# 赋予脚本执行权限
chmod +x scripts/fix_alembic_version.sh

# 执行修复
bash scripts/fix_alembic_version.sh
```

#### 3. 验证修复结果

脚本执行成功后，会输出：
```
[INFO] ✅ 版本修正完成: 20260809_0023 → 20260809_0001
[INFO] 下一步请执行: alembic stamp head
```

#### 4. 标记为最新版本

```bash
# 进入 admin-api 容器
docker exec -it deploy-admin-api-1 bash

# 标记 alembic 为最新版本（不实际执行 SQL，因为表结构已完整）
cd /app
alembic stamp head

# 验证版本
alembic current
# 应输出: 20260809_0001 (head)
```

#### 5. 重新部署

```bash
# 退出容器
exit

# 重新执行部署脚本
cd /opt/fangyu-defense-system
bash deploy/deploy.sh
```

---

### 方案二：手动修复数据库（备选）

如果无法使用脚本，可以手动修正数据库：

#### 1. 连接数据库

```bash
mysql -h your_db_host -u root -p fangyu_defense
```

#### 2. 查看当前版本

```sql
SELECT * FROM alembic_version;
```

#### 3. 更新版本号

```sql
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('20260809_0001');
```

#### 4. 后续步骤

参考方案一的第 4-5 步。

---

## 预防措施

### 1. 迁移文件合并流程规范

今后如需合并历史迁移文件，应遵循以下流程：

1. **开发环境验证**：在本地完整测试合并后的迁移链
2. **生成兼容性脚本**：自动生成版本修正脚本（如本次的 `fix_alembic_version.sh`）
3. **文档同步更新**：更新部署文档，标注需要执行修复脚本
4. **生产环境预演**：在预发布环境完整走一遍流程
5. **灰度发布**：先在单台服务器验证，再全量部署

### 2. 数据库迁移操作检查清单

部署前必须检查：
- [ ] `alembic_version` 表当前版本号
- [ ] 新迁移链是否包含该版本号
- [ ] 是否需要执行版本修正脚本
- [ ] 迁移文件是否已在开发/测试环境验证

---

## 常见问题

### Q1: 脚本执行报错 "Access denied for user"

**原因**：数据库密码错误或用户权限不足

**解决**：
```bash
# 检查密码是否正确
echo $DB_PASSWORD

# 检查用户权限
mysql -u root -p -e "SHOW GRANTS FOR 'root'@'%';"
```

### Q2: alembic stamp head 报错 "Can't locate revision"

**原因**：`alembic_version` 表尚未修正

**解决**：先执行方案一的第 1-3 步，确保版本号已更新为 `20260809_0001`

### Q3: 如何回滚到旧迁移链？

**方案**：
```bash
# 1. 回滚代码到合并前的 commit
git checkout <commit_before_merge>

# 2. 重新构建镜像
docker-compose build admin-api

# 3. 重新部署
bash deploy/deploy.sh
```

---

## 技术细节

### alembic_version 表结构

```sql
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);
```

该表只有一行记录，存储当前数据库的迁移版本号。

### alembic stamp 命令说明

```bash
alembic stamp head
```

- **作用**：标记数据库为指定版本，但不实际执行 SQL
- **适用场景**：数据库表结构已完整，只需修正版本号
- **与 upgrade 的区别**：`upgrade` 会执行迁移 SQL，`stamp` 只更新版本记录

---

## 相关文件

- **修复脚本**：`/scripts/fix_alembic_version.sh`
- **合并后的迁移文件**：`/admin-api/alembic/versions/20260809_0001_initial_complete_schema.py`
- **部署脚本**：`/deploy/deploy.sh`
- **问题排查报告**：`/docs/troubleshooting/issue_report_20260809.md`

---

## 总结

本次迁移版本冲突是由于代码仓库迁移链与生产数据库版本号不同步导致的。修复方案的核心思路是：

1. **手动修正数据库版本号**：将 `alembic_version` 表的 `version_num` 从 `20260809_0023` 改为 `20260809_0001`
2. **标记为最新版本**：使用 `alembic stamp head` 将当前状态标记为最新
3. **重新部署**：确保所有服务使用新的迁移链

后续应建立完善的迁移文件管理规范，避免类似问题再次发生。
