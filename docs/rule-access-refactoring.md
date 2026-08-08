# 站点接入规则重构说明

## 重构目标

本次重构优化了站点管理中的规则接入机制，解决了以下问题：

1. **消除硬编码**：移除前端 API 中的 `siteId=0` 硬编码
2. **统一接口风格**：规则操作统一使用全局路由，不再依赖站点路径参数
3. **清晰的职责划分**：规则与站点的绑定关系通过专用接口管理
4. **保持向后兼容**：保留站点级查询接口用于展示站点绑定的规则

## 架构变更

### V3 两层架构

```
应用 (Application)
  └── 站点 (Site)
       └── 规则 (Rule) - 多对多关联
```

- **应用层**：应用是顶层容器，用于组织多个站点
- **站点层**：站点是具体的业务站点，归属于某个应用
- **规则层**：规则是全局资源，通过 `biz_rule_site` 关联表绑定到站点

### 数据模型

**站点模型 (SiteModel)**
```python
class SiteModel:
    id: int                          # 站点主键
    site_key: str                    # 站点标识（site_<hex8>）
    app_id: int                      # 所属应用ID
    name: str                        # 站点名称
    domain: str                      # 主域名
    alt_domains: list[str]           # 备用域名
    access_mode: str                 # 接入模式：adapter/sdk
    site_secret: str                 # 站点密钥
    sdk_version: str | None          # SDK版本
    gateway_url: str | None          # 专属网关地址
    is_active: bool                  # 是否启用
    clock_stats_enabled: bool        # 是否启用频控统计
    log_retention_days: int          # 日志保留天数
    remark: str | None               # 备注
```

**规则-站点关联表 (RuleSiteModel)**
```python
class RuleSiteModel:
    id: int                          # 主键
    rule_id: int                     # 规则ID
    site_id: int                     # 站点ID
    created_at: datetime             # 创建时间
```

## API 变更

### 后端接口变更

#### 新增全局规则接口

| 方法 | 路径 | 说明 |
|------|------|------|
| DELETE | `/api/v2/rules/{rule_id}` | 删除规则（全局接口） |
| POST | `/api/v2/rules/{rule_id}/publish` | 发布规则（全局接口） |
| POST | `/api/v2/rules/{rule_id}/shadow` | 灰度影子（全局接口） |
| POST | `/api/v2/rules/{rule_id}/disable` | 停用规则（全局接口） |
| POST | `/api/v2/rules/{rule_id}/archive` | 归档规则（全局接口） |
| POST | `/api/v2/rules/{rule_id}/unarchive` | 恢复规则（全局接口） |
| GET | `/api/v2/rules/{rule_id}/versions` | 规则版本列表（全局接口） |
| POST | `/api/v2/rules/{rule_id}/rollback` | 规则回滚（全局接口） |

#### 保留的站点级接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v2/sites/{site_id}/rules` | 查询站点绑定的规则列表 |
| POST | `/api/v2/sites/{site_id}/rules` | 在站点下创建规则并绑定 |
| GET | `/api/v2/sites/{site_id}/rules/{rule_id}` | 查询规则详情（需验证权限） |
| PUT | `/api/v2/sites/{site_id}/rules/{rule_id}` | 更新规则（需验证权限） |
| POST | `/api/v2/sites/{site_id}/rules/sync-cache` | 同步站点规则缓存 |

#### 规则绑定接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v2/rules/{rule_id}/set-sites` | 全量覆盖规则绑定的站点列表 |
| POST | `/api/v2/rules/bind-to-site/{site_id}` | 全量覆盖站点绑定的规则列表 |

### 前端接口变更

#### 修改前（使用硬编码）

```typescript
// ❌ 旧版本：硬编码 siteId=0
export function fetchDeleteRule(ruleId: number) {
  return request.del<null>({
    url: `/api/v2/sites/0/rules/${ruleId}`  // 硬编码
  })
}

export function fetchPublishRule(ruleId: number) {
  return request.post<Api.Fangyu.Rule>({
    url: `/api/v2/sites/0/rules/${ruleId}/publish`  // 硬编码
  })
}
```

#### 修改后（使用全局接口）

```typescript
// ✅ 新版本：使用全局接口
export function fetchDeleteRule(ruleId: number) {
  return request.del<null>({
    url: `/api/v2/rules/${ruleId}`
  })
}

export function fetchPublishRule(ruleId: number, data?: { change_summary?: string }) {
  return request.post<Api.Fangyu.Rule>({
    url: `/api/v2/rules/${ruleId}/publish`,
    data
  })
}
```

## 业务逻辑优化

### 规则绑定流程

**1. 设置规则的站点列表**
```typescript
// 将规则绑定到多个站点
await fetchSetRuleSites(ruleId, [siteId1, siteId2, siteId3])
```

后端逻辑：
- 全量覆盖规则的站点绑定关系
- 对于已发布的规则，自动同步 Redis 缓存
- 移除的站点：从缓存中删除该规则
- 新增的站点：将规则写入缓存

**2. 设置站点的规则列表**
```typescript
// 将多条规则绑定到站点
const result = await fetchBindRulesToSite(siteId, [ruleId1, ruleId2, ruleId3])
// result.data.bound: 绑定的规则数量
// result.data.conflicts: 冲突检测结果
```

后端逻辑：
- 全量覆盖站点的规则绑定关系
- 重建该站点的 Redis 缓存分片
- 执行规则冲突检测，返回冲突信息

### 缓存同步机制

**站点级缓存同步**
```typescript
// 重建单个站点的规则缓存
await fetchPublishSiteRules(siteId)

// 批量重建多个站点的规则缓存
await fetchBatchPublishSites([siteId1, siteId2, siteId3])
```

Redis 存储结构：
```
fangyu:rules:{site_id} -> Hash
  - {rule_id} -> JSON(rule_snapshot)
```

**同步时机**：
1. 规则发布/停用/归档时自动同步所有绑定站点
2. 修改规则绑定关系时自动同步受影响站点
3. 手动调用同步接口强制重建

## 接入模式说明

### access_mode 字段

站点支持两种接入模式：

**1. adapter（适配器模式）**
- 使用 Nginx-Lua 适配器或 WordPress 插件
- 在服务器端拦截请求
- 适用于传统 Web 应用

**2. sdk（浏览器 SDK 模式）**
- 使用 embed.js 浏览器 SDK
- 在客户端执行防护逻辑
- 适用于现代 SPA 应用

### SDK 配置示例

```javascript
// 前端 SDK 配置
SdSdk.guard({
  apiKey: site.site_key,  // 站点标识（site_<hex8>）
  appId: site.id          // 站点数字主键，用于租户隔离
})
```

**注意**：
- `apiKey` 使用站点的 `site_key`（字符串标识）
- `appId` 使用站点的 `id`（数字主键），**不是** `app_id`（所属应用ID）

## 迁移指南

### 前端代码迁移

#### 1. 更新导入的 API 函数

所有规则操作相关的 API 函数已移除 `siteId` 参数：

```typescript
// 修改前
await fetchDeleteRule(siteId, ruleId)
await fetchPublishRule(siteId, ruleId)
await fetchDisableRule(siteId, ruleId)

// 修改后
await fetchDeleteRule(ruleId)
await fetchPublishRule(ruleId)
await fetchDisableRule(ruleId)
```

#### 2. 更新规则绑定逻辑

```typescript
// 修改前：无统一的绑定接口

// 修改后：使用专用的绑定接口
// 方式1：从规则维度设置站点列表
await fetchSetRuleSites(ruleId, siteIds)

// 方式2：从站点维度设置规则列表（带冲突检测）
const { bound, conflicts } = await fetchBindRulesToSite(siteId, ruleIds)
```

### 后端代码迁移

#### 1. 服务层无需修改

`RuleService` 和 `SiteService` 的方法签名保持不变，只是调用方式更新。

#### 2. 路由层已自动兼容

- 站点级路由保留，用于站点维度的查询和操作
- 全局路由新增，用于跨站点的规则管理
- 两套路由可以共存，互不影响

## 测试建议

### 单元测试

1. **规则绑定测试**
   - 测试 `set_sites` 方法正确更新关联关系
   - 测试 `bind_rules_to_site` 方法正确更新关联关系
   - 测试绑定后缓存同步是否正确

2. **缓存同步测试**
   - 测试规则发布后所有绑定站点的缓存已更新
   - 测试规则停用后所有绑定站点的缓存已移除
   - 测试修改绑定关系后缓存增量同步

### 集成测试

1. **接口测试**
   - 测试所有全局路由接口返回正确
   - 测试站点级路由接口权限校验正确
   - 测试规则绑定接口的冲突检测功能

2. **端到端测试**
   - 创建站点 → 创建规则 → 绑定规则 → 发布规则 → 验证缓存
   - 修改绑定 → 验证缓存更新
   - 删除绑定 → 验证缓存清除

## 注意事项

### 1. 权限校验

全局路由的权限校验：
- 规则查询：`rule.read`
- 规则编辑：`rule.write`
- 规则发布/停用：`rule.publish`

站点级路由的权限校验：
- 在权限基础上增加站点可见性检查
- 全局规则（`site_id=0`）对所有站点可见
- 站点专属规则只对绑定的站点可见

### 2. 缓存一致性

- 规则状态变更时自动同步缓存，无需手动调用
- 仅在缓存异常或数据不一致时才需要手动同步
- 批量操作时使用批量同步接口提升性能

### 3. 向后兼容

- 保留站点级路由用于特定场景
- 前端可以混用全局接口和站点接口
- 建议新代码优先使用全局接口

## 相关文档

- [API 契约文档](./api/API_CONTRACTS.md)
- [V3 语义冲突修复报告](./v3-semantic-conflict-fix-report.md)
- [应用-站点分离迁移指南](./migration-app-site-separation.md)
