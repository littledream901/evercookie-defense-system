# 临时脚本目录

本目录存放一次性调试脚本、临时验证脚本、数据分析脚本。

## 规则约定

根据项目编码规范 [DIR-004] 和 [DIR-005]：

- **存放范围**：仅限本地调试、临时验证、一次性数据处理脚本
- **生命周期**：默认 7 天，超期可自动清理
- **升级规则**：复用 3 次及以上的脚本必须迁移至 `/scripts/` 长期目录
- **禁止提交**：本目录所有文件已纳入 `.gitignore`，禁止提交到版本控制
- **敏感数据**：禁止在脚本中硬编码密钥、生产数据、用户隐私信息

## 当前可用脚本

### check_inactive_sites.py

**用途**：检查已停用站点是否仍有流量尝试访问

**使用场景**：
- 后台删除站点后，怀疑外部适配器（CF Worker/Nginx）未清理
- 定期巡检，发现需要清理的历史站点

**执行方式**：
```bash
# 在项目根目录或 admin-api 容器内执行
python tmp/scripts/check_inactive_sites.py
```

**输出示例**：
```
======================================================================
检查已停用站点是否仍有流量尝试访问
======================================================================

[1/3] 从数据库读取已停用站点...
✓ 发现 3 个已停用站点

[2/3] 检查 Redis 映射状态...
✓ 完成检查

[3/3] 分析结果
----------------------------------------------------------------------
⚠ 发现 2 个异常情况：

站点 ID: 123 | 名称: 旧站点A | 域名: old-a.com
  停用时间: 2 小时前
  Redis 状态: exists=True, is_active=True
  ⚠ 严重：数据库标记已停用，但 Redis 仍标记为激活
  建议：执行 Redis 迁移脚本或手动更新 Redis 值
  命令：redis-cli GET 'fangyu:app_keys:site_abc123'
  建议：检查 Cloudflare Worker 或 Nginx 适配器是否已清理
```

---

## 脚本开发规范

编写临时脚本时遵循以下规范：

### 1. 文件命名

```
✓ 好的命名：
  - verify_bug_1234.py        # 验证特定 Bug
  - analyze_decision_logs.py   # 数据分析
  - test_redis_connection.py   # 临时测试

✗ 不好的命名：
  - test.py                    # 太泛化
  - aaa.py                     # 无意义
  - script1.py                 # 编号命名
```

### 2. 脚本结构

每个脚本应包含：

```python
#!/usr/bin/env python3
"""脚本用途的简短说明。

详细说明：
- 解决什么问题
- 使用场景
- 执行方式
- 注意事项

示例：
    python tmp/scripts/xxx.py --arg value
"""

# 你的代码...

if __name__ == "__main__":
    main()
```

### 3. 环境变量

临时脚本可以硬编码测试值，但必须：

```python
# ✓ 好的做法
TEST_SITE_ID = 9999  # 测试用站点 ID，非生产数据
DB_URL = os.getenv("ADMIN_DATABASE_URL", "sqlite:///test.db")

# ✗ 不好的做法
PROD_DB_PASSWORD = "real_password_123"  # 禁止硬编码生产凭据
API_KEY = "sk_live_xxx"                 # 禁止硬编码真实 Key
```

### 4. 清理规则

符合以下条件的脚本应迁移到 `/scripts/`：

- 复用 3 次及以上
- 解决长期存在的问题
- 需要在 CI/CD 中调用
- 需要团队其他成员使用

迁移步骤：

```bash
# 1. 移动文件
mv tmp/scripts/useful_script.py scripts/

# 2. 更新导入路径（如有）
# 3. 编写文档说明
# 4. 提交到版本控制
git add scripts/useful_script.py
git commit -m "feat: 迁移临时脚本到长期目录"
```

---

## 常见临时脚本场景

### 场景 1：验证 Bug 修复

```python
#!/usr/bin/env python3
"""验证 Bug #1234 是否已修复。

Bug 描述：站点删除后仍产生访问日志
验证方法：检查已删除站点的 Redis 映射是否清理
"""
# 验证逻辑...
```

### 场景 2：数据分析

```python
#!/usr/bin/env python3
"""分析最近 7 天的决策日志，统计各站点的拦截率。

输出：CSV 文件到 tmp/data/block_rate_analysis.csv
"""
# 分析逻辑...
```

### 场景 3：临时数据修复

```python
#!/usr/bin/env python3
"""一次性修复：批量更新站点的 log_retention_days。

背景：历史站点默认值为 7 天，需统一改为 30 天
影响：约 50 个站点
"""
# 修复逻辑...
```

### 场景 4：环境检查

```python
#!/usr/bin/env python3
"""检查部署环境配置是否正确。

检查项：
- Redis 连接
- MySQL 连接
- ClickHouse 连接
- 环境变量完整性
"""
# 检查逻辑...
```

---

## 自动清理

项目定期运行清理任务（TODO：待实现）：

```bash
# 清理超过 7 天未修改的脚本
find tmp/scripts -name "*.py" -mtime +7 -delete

# 清理超过 7 天的临时数据
find tmp/data -type f -mtime +7 -delete
```

手动清理：

```bash
# 清理所有临时脚本（谨慎操作）
rm -rf tmp/scripts/*

# 清理特定脚本
rm tmp/scripts/obsolete_script.py
```

---

## 参考文档

- [项目编码规范](../../docs/project-rule.md)
- [目录管理规范 - DIR 章节](../../docs/project-rule.md#2-目录与文件管理规范dir)
- [临时文件处理指南](../../docs/ops/temporary-files-guide.md)
