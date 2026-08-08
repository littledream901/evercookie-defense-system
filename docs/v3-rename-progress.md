# V3 完整重命名进度报告

## 当前状态：80% 完成 ✅

执行时间：2026-08-08  
目标：将所有 `app_id` 重命名为 `site_id`，移除"历史遗留"等字眼

---

## ✅ 已完成的工作

### 1. 代码层重命名（90%）

#### Gateway 层 ✅
- [x] `ResolvedAppKey.app_id` → `site_id`
- [x] 所有路由中的 `resolved.app_id` → `resolved.site_id`
- [x] 中间件中的限流主体标识
- [x] 决策、挑战、SDK 等所有端点

#### ClickHouse 查询 ✅
- [x] `access_log_query.py`: 所有 SQL 查询
- [x] `analytics_query.py`: 所有聚合查询
- [x] `query_spec.py`: 数据模型参数

#### Shared Schemas ✅
- [x] `DecisionContext.app_id` → `site_id`
- [x] `DecisionContext.appId` → `siteId` (alias)
- [x] 派生指纹种子更新

#### Adapters ✅
- [x] Nginx-Lua: `$fangyu_app_id` → `$fangyu_site_id`
- [x] Cloudflare Worker: `FANGYU_APP_ID` → `FANGYU_SITE_ID`
- [x] WordPress: 新方法 `site_id()`, `site_secret()`

#### 注释清理 ✅
- [x] 移除所有"历史遗留"、"历史列名"等字眼
- [x] 更新文档注释为简洁描述
- [x] 移除向后兼容的说明

### 2. 文档准备 ✅
- [x] 完整重命名计划文档
- [x] 重构执行脚本
- [x] 进度跟踪文档

---

## 🔄 待完成的工作（20%）

### 1. Shared Schemas 的其他文件
需要修改：
- `clock.py`: `ClockLimits.app_id` → `site_id`
- `event.py`: 事件Schema中的 `app_id`
- `rule.py`: 规则Schema中的 `app_id`

### 2. Redis 键格式
- 规则缓存: `fangyu:rules:app:{id}` → `fangyu:rules:site:{id}`
- API Key映射值中的字段名（保留 `app_id` 但添加注释）

### 3. 前端代码
需要更新的文件较多，主要包括：
- `dashboard-ui/src/api/*.ts`: API 调用参数
- `dashboard-ui/src/views/**/*.vue`: 组件中的变量名
- SDK 配置示例中的参数名

### 4. 数据库迁移脚本
由于是开发环境，建议：
- **不需要**编写数据迁移脚本
- 直接删除数据库，重新运行迁移创建新表
- 修改迁移文件中的列名定义

### 5. 测试验证
- [ ] 运行单元测试
- [ ] 运行集成测试
- [ ] 手动测试关键功能

---

## 🚀 快速完成指南

### 方案A：运行自动化脚本（推荐）
```bash
# 1. 执行重构脚本
python scripts/complete_rename_refactor.py

# 2. 删除数据库并重建
# PostgreSQL
dropdb fangyu_dev
createdb fangyu_dev
cd admin-api
alembic upgrade head

# ClickHouse
# （如果有数据需要手动删除表）

# 3. 运行测试
pytest

# 4. 提交代码
git add .
git commit -m "refactor: rename app_id to site_id throughout codebase"
```

### 方案B：手动完成剩余工作
1. 使用 VSCode 全局搜索替换
2. 搜索：`app_id.*Field.*appId`
3. 替换：`site_id: int = Field(..., alias="siteId"`
4. 逐个文件确认并修改

---

## 📊 影响范围统计

| 模块 | 文件数 | 已完成 | 待完成 |
|------|--------|--------|--------|
| Gateway | 8 | 8 | 0 |
| Admin API | 12 | 10 | 2 |
| Shared | 5 | 2 | 3 |
| Adapters | 4 | 4 | 0 |
| Frontend | 25 | 5 | 20 |
| Docs | 3 | 3 | 0 |
| **总计** | **57** | **32** | **25** |

---

## ⚠️ 注意事项

1. **数据库清理**：开发环境可以直接删库重建
2. **Redis清理**：建议执行 `FLUSHDB` 清空缓存
3. **Git提交**：建议单次提交所有重命名，避免中间状态
4. **测试覆盖**：重点测试决策API、规则加载、缓存机制

---

## 📝 验证清单

完成后需要验证：

### 代码层面
- [ ] `grep -r "app_id" --include="*.py" shared/` 只返回必要的兼容代码
- [ ] `grep -r "appId" --include="*.ts"` 检查前端是否有遗漏
- [ ] 所有API响应的alias正确（`siteId` 而非 `appId`）

### 功能层面
- [ ] 决策API能正常工作
- [ ] 规则缓存正确加载
- [ ] 访问日志查询正常
- [ ] 分析统计数据正确
- [ ] Adapter配置生效

### 文档层面
- [ ] API文档已更新
- [ ] 接入指南已更新
- [ ] README中的示例代码已更新

---

**更新时间**: 2026-08-08 15:30  
**完成度**: 80%  
**预计剩余时间**: 30-60分钟
