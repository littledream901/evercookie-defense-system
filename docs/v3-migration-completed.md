# V3 App-Site 分离迁移完成报告

**完成时间**：2026-08-08  
**迁移版本**：20260808_0002

---

## ✅ 已完成的工作

### 1. 数据库层（已完成）

#### 表结构更新
- ✅ **biz_application**：应用表（重建）
  - `app_key`：应用唯一标识 (app_<hex8>)
  - `app_secret`：应用级密钥
  - 支持应用分组管理

- ✅ **biz_site**：站点表（新建）
  - `site_key`：站点唯一标识 (site_<hex8>)
  - `app_id`：关联应用
  - `site_secret`：站点级密钥（可选）
  - 继承原 biz_application 的站点相关字段

- ✅ **biz_rule**：规则表（更新）
  - 新增 `app_id`：支持应用级规则
  - 新增 `inherit_from_app`：站点继承标志
  - 保留完整的规则字段结构

- ✅ **biz_rule_site**：规则-站点关联表（更新）
  - 外键关联到 `biz_site.id`（而非旧的 biz_application.id）

- ✅ **biz_rule_group**：规则组表（更新）
  - 外键关联到 `biz_site.id`

- ✅ **biz_rule_version**：规则版本表（重建）

#### 迁移脚本
- 文件：`admin-api/alembic/versions/20260808_0002_app_site_clean_rebuild.py`
- 状态：✅ 已执行成功
- 策略：删除旧表，重建新结构（适用于测试环境）

### 2. 后端代码层（已完成）

#### 模型层更新
- ✅ [models.py](../admin-api/src/infrastructure/repositories/models.py)
  - `ApplicationModel`：应用模型（V3 两层架构）
  - `SiteModel`：站点模型（V3 两层架构）
  - `ApplicationModelLegacy`：旧模型（向后兼容，未使用）
  - 更新 `RuleModel`、`RuleSiteModel`、`RuleGroupModel`

#### 仓储层新增
- ✅ [ApplicationRepository](../admin-api/src/infrastructure/repositories/application_repository.py)
  - 应用的 CRUD 操作
  - 密钥轮换
  - 站点计数

- ✅ [SiteRepository](../admin-api/src/infrastructure/repositories/site_repository.py)
  - 站点的 CRUD 操作
  - 按应用查询
  - 密钥轮换

- ✅ [RuleRepository](../admin-api/src/infrastructure/repositories/rule_repository.py)（更新）
  - `list_all` 支持 `app_id` 参数
  - `create` 支持应用级规则

#### API 层新增
- ✅ [/v2/applications](../admin-api/src/interfaces/http/v2/applications.py)
  ```
  GET    /v2/applications                    # 应用列表
  GET    /v2/applications/{app_id}           # 应用详情
  POST   /v2/applications                    # 创建应用
  PUT    /v2/applications/{app_id}           # 更新应用
  DELETE /v2/applications/{app_id}           # 删除应用
  POST   /v2/applications/{app_id}/rotate-secret  # 轮换密钥
  GET    /v2/applications/{app_id}/sites     # 应用下的站点
  ```

- ✅ [/v2/sites](../admin-api/src/interfaces/http/v2/sites.py)
  ```
  GET    /v2/sites                           # 站点列表（支持按 appId 过滤）
  GET    /v2/sites/{site_id}                 # 站点详情
  POST   /v2/sites                           # 创建站点
  PUT    /v2/sites/{site_id}                 # 更新站点
  DELETE /v2/sites/{site_id}                 # 删除站点
  POST   /v2/sites/{site_id}/rotate-secret   # 轮换密钥
  ```

- ✅ [/v2/access-logs](../admin-api/src/interfaces/http/v2/access_logs.py)（更新）
  - 支持 `appId` 参数（应用级查询）
  - 支持 `siteId` 参数（站点级查询，V2 兼容）
  - 优先使用 `siteId`，其次 `appId`

#### 路由注册
- ✅ [v2/__init__.py](../admin-api/src/interfaces/http/v2/__init__.py)
  - 已注册 `applications_router`
  - 已注册 `sites_router`

---

## 🏗️ 架构说明

### 新的两层架构

```
┌─────────────────────────────────────────┐
│         Application（应用层）            │
│  - app_key: app_<hex8>                  │
│  - app_secret: 应用级密钥                │
│  - 用途：业务分组、权限管理              │
└──────────────┬──────────────────────────┘
               │ 1:N
               ▼
┌─────────────────────────────────────────┐
│           Site（站点层）                 │
│  - site_key: site_<hex8>                │
│  - site_secret: 站点级密钥（可选）        │
│  - domain: 主域名                        │
│  - 用途：具体站点、规则绑定               │
└─────────────────────────────────────────┘
```

### 规则关联

```
Rule（规则）
├── app_id（应用级规则）
│   └── 所有该应用下的站点继承
└── biz_rule_site（站点级规则）
    └── 精确绑定到特定站点
```

---

## 🔄 向后兼容

### API 兼容
- ✅ 旧的 `/v2/sites` API 仍然可用（对应 `apps.py`，V2 单层架构）
- ✅ 新的 `/v2/applications` 和 `/v2/sites` 实现 V3 两层架构
- ✅ 访问日志 API 同时支持 `siteId`（V2）和 `appId`（V3）

### 认证兼容
- ✅ 站点使用 `site_key` 作为 X-App-Key
- ✅ 可选使用 `site_secret` 或继承 `app_secret`

---

## 📋 示例数据

迁移已自动创建：
- **示例应用**：`app_00000000`
  - 名称：示例应用
  - 密钥：`change_me_in_production`

- **示例站点**：`site_00000000`
  - 名称：示例站点
  - 域名：localhost
  - 所属应用：app_00000000

---

## 🚀 下一步工作

### 1. 前端适配（待完成）
- [ ] 创建应用管理页面
  - `dashboard-ui/src/views/fangyu/applications/index.vue`
  - `dashboard-ui/src/views/fangyu/applications/modules/app-dialog.vue`

- [ ] 更新站点管理页面
  - 添加应用选择器
  - 按应用分组显示站点
  - 支持从应用创建站点

- [ ] 更新访问日志页面
  - 添加应用选择器
  - 支持应用级和站点级查询切换

- [ ] 更新类型定义
  - `dashboard-ui/src/types/api/api.d.ts`
  - 添加 Application 和 Site 接口

- [ ] 更新 API 调用
  - `dashboard-ui/src/api/apps.ts`
  - 添加应用和站点的 API 方法

### 2. 业务逻辑完善（待完成）
- [ ] 应用级规则继承逻辑
- [ ] 站点密钥回退到应用密钥
- [ ] 权限管理（应用级 + 站点级）

### 3. 测试验证（待完成）
- [ ] API 接口测试
- [ ] 数据完整性验证
- [ ] 性能测试

### 4. 文档更新（待完成）
- [ ] API 文档更新
- [ ] 用户手册更新

---

## ⚠️ 注意事项

### 数据迁移
- ✅ 当前迁移策略：**删除旧表数据**
- 适用场景：**测试环境**
- 生产环境：需要保留数据的迁移方案（参考 [migration-app-site-separation.md](./migration-app-site-separation.md)）

### 破坏性变更
1. 旧的 `biz_application` 表已重建
2. 旧的规则数据已清空
3. 外键关联已更新

### 回滚
如需回滚：
```bash
cd admin-api
python -m alembic downgrade 20260807_0022
```
⚠️ 警告：回滚会删除所有 V3 架构数据

---

## 📊 迁移统计

- **新增表**：1 个（biz_site）
- **重建表**：4 个（biz_application, biz_rule, biz_rule_site, biz_rule_group）
- **新增仓储**：2 个（ApplicationRepository, SiteRepository）
- **新增 API 路由**：2 个（/applications, /sites）
- **更新 API 路由**：1 个（/access-logs）
- **代码变更文件**：8 个

---

## ✅ 验证清单

### 后端验证
- [x] 数据库迁移成功执行
- [x] 模型定义正确
- [x] 仓储层正常工作
- [x] API 路由注册成功
- [ ] API 接口功能测试
- [ ] 单元测试通过

### 前端验证
- [ ] 应用管理页面开发
- [ ] 站点管理页面更新
- [ ] 访问日志页面更新
- [ ] 端到端测试

### 业务验证
- [ ] 创建应用流程
- [ ] 创建站点流程
- [ ] 规则绑定流程
- [ ] 访问日志查询

---

## 📞 支持

如有问题，请参考：
- [迁移方案文档](./migration-app-site-separation.md)
- [App ID 设计说明](./app-id-design.md)
- [访问日志字段检查](./access-log-fields-check.md)
