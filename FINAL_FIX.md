# 迁移失败修复 - 最终方案

## 问题现象

版本号已修复成功，但部署时仍报错：
```
Can't locate revision identified by '20260809_0023'
```

## 根本原因

Docker 镜像构建时包含了旧的 Python `__pycache__` 文件，导致 Alembic 仍在查找已删除的迁移版本。

---

## ✅ 解决方案（生产服务器执行）

### 方案 1：使用清理脚本（推荐）

```bash
cd /opt/fangyu-defense-system
git pull origin v3-app-site-separation

# 执行清理并重新构建脚本
bash deploy/scripts/rebuild_clean.sh
```

### 方案 2：手动清理（如果脚本失败）

```bash
cd /opt/fangyu-defense-system

# 1. 清理本地 Python 缓存
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# 2. 清理 Docker 构建缓存
docker builder prune -f

# 3. 删除旧镜像（可选）
docker images | grep fangyu | awk '{print $1":"$2}' | xargs -r docker rmi

# 4. 使用 --no-cache 重新构建
DOCKER_BUILDKIT=1 docker compose -f deploy/docker-compose.prod.yml build --no-cache --pull

# 5. 执行部署
bash deploy/deploy.sh update
```

---

## 📋 操作总结

已完成的修复：
1. ✅ 清理了本地 `__pycache__` 缓存
2. ✅ 修复了数据库版本号（`20260809_0023` → `20260809_0001`）
3. ✅ 创建了清理重建脚本

还需执行：
- ⏳ 清理 Docker 构建缓存
- ⏳ 使用 `--no-cache` 重新构建镜像
- ⏳ 重新部署

---

## 🔍 验证步骤

部署成功后验证：

```bash
# 1. 检查迁移版本
docker compose -f deploy/docker-compose.prod.yml exec admin-api alembic current
# 应显示：20260809_0001 (head)

# 2. 检查服务状态
bash deploy/deploy.sh verify

# 3. 查看服务日志
bash deploy/deploy.sh logs admin-api
```

---

## ⚠️ 重要提示

- 数据库版本号已正确修复，**不要再次运行** `fix_alembic_version_simple.sh`
- 问题出在 Docker 镜像缓存，需要清理缓存重新构建
- 备份已在部署过程中自动完成（步骤 [2]）

---

## 📁 相关文件

- 清理重建脚本：`deploy/scripts/rebuild_clean.sh`
- 版本修复脚本：`deploy/scripts/fix_alembic_version_simple.sh`（已完成，无需再次执行）
- 部署脚本：`deploy/deploy.sh`
