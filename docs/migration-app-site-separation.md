# Application-Site 两层架构迁移方案

## 📋 迁移概述

**目标**：将当前的单层 Application 架构升级为两层 App-Site 架构

**原架构**：1个 Application = 1个站点
**新架构**：1个 Application（应用/分组） → N个 Site（具体站点）

---

## 🎯 迁移目标

### 核心变化

| 维度 | 当前 | 迁移后 |
|------|------|--------|
| **表结构** | `biz_application` | `biz_application` (应用) + `biz_site` (站点) |
| **主键** | `id` (app_id) | `app.id` (app_id) + `site.id` (site_id) |
| **外部标识** | `site_id` (字符串) | `app_key` + `site_key` |
| **规则关联** | 关联 application.id | 关联 site.id（支持继承 app_id） |
| **ClickHouse** | `app_id` | `app_id` + `site_id` 双分区 |

---

## 📐 新数据模型

### 1. Application 表（应用层）

```sql
CREATE TABLE biz_application (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '应用主键（app_id）',
    app_key VARCHAR(32) UNIQUE NOT NULL COMMENT '应用唯一标识 app_<hex8>',
    name VARCHAR(128) NOT NULL COMMENT '应用名称',
    description VARCHAR(512) DEFAULT '' COMMENT '应用描述',
    owner_user_id BIGINT COMMENT '应用所有者',
    app_secret VARCHAR(128) NOT NULL COMMENT '应用级密钥',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    
    INDEX idx_owner (owner_user_id),
    INDEX idx_active (is_active)
) COMMENT='应用表（业务分组）';
```

### 2. Site 表（站点层）

```sql
CREATE TABLE biz_site (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '站点主键（site_id）',
    site_key VARCHAR(32) UNIQUE NOT NULL COMMENT '站点唯一标识 site_<hex8>',
    app_id BIGINT NOT NULL COMMENT '所属应用',
    name VARCHAR(128) NOT NULL COMMENT '站点名称',
    domain VARCHAR(512) NOT NULL COMMENT '主域名',
    alt_domains JSON COMMENT '备用域名列表',
    access_mode VARCHAR(16) DEFAULT 'adapter' COMMENT '接入模式：adapter/sdk',
    site_secret VARCHAR(128) DEFAULT '' COMMENT '站点级密钥（可选）',
    sdk_version VARCHAR(16) COMMENT 'SDK 版本',
    gateway_url VARCHAR(512) COMMENT '专属网关地址',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    clock_stats_enabled BOOLEAN DEFAULT TRUE COMMENT '是否启用频控统计',
    log_retention_days INT DEFAULT 30 COMMENT '日志保留天数',
    remark TEXT COMMENT '备注',
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
    
    FOREIGN KEY (app_id) REFERENCES biz_application(id) ON DELETE CASCADE,
    INDEX idx_app_id (app_id),
    INDEX idx_domain (domain(255)),
    INDEX idx_active (is_active)
) COMMENT='站点表（具体站点）';
```

### 3. Rule 表更新

```sql
-- 规则表添加 app_id 支持应用级规则
ALTER TABLE biz_rule 
ADD COLUMN app_id BIGINT COMMENT '应用级规则（关联应用，为空则全局）',
ADD COLUMN inherit_from_app BOOLEAN DEFAULT FALSE COMMENT '站点是否继承应用规则',
ADD INDEX idx_app_id (app_id);
```

### 4. Rule-Site 关联表更新

```sql
-- 更新外键关联到新的 biz_site 表
ALTER TABLE biz_rule_site
DROP FOREIGN KEY biz_rule_site_ibfk_2,
ADD FOREIGN KEY (site_id) REFERENCES biz_site(id) ON DELETE CASCADE;
```

### 5. Rule Group 表更新

```sql
-- 规则组关联站点
ALTER TABLE biz_rule_group
DROP FOREIGN KEY biz_rule_group_ibfk_1,
ADD FOREIGN KEY (site_id) REFERENCES biz_site(id) ON DELETE CASCADE;
```

---

## 🔄 数据迁移策略

### 阶段 1：表结构迁移（不中断服务）

1. **创建新表**
   - 创建 `biz_application_new`（临时表）
   - 创建 `biz_site`

2. **数据转换**
   ```sql
   -- 为每个现有站点创建默认应用
   INSERT INTO biz_application_new (app_key, name, description, owner_user_id, app_secret, is_active, created_at, updated_at)
   SELECT 
       CONCAT('app_', SUBSTRING(site_id, 6)) as app_key,  -- site_abc123 → app_abc123
       CONCAT(name, ' (应用)') as name,
       description,
       owner_user_id,
       app_secret,
       is_active,
       created_at,
       updated_at
   FROM biz_application;
   
   -- 将现有站点迁移到 biz_site
   INSERT INTO biz_site (site_key, app_id, name, domain, alt_domains, access_mode, site_secret, 
                         sdk_version, gateway_url, is_active, clock_stats_enabled, log_retention_days, 
                         remark, created_at, updated_at)
   SELECT 
       a_old.site_id as site_key,
       a_new.id as app_id,
       a_old.name,
       a_old.domain,
       a_old.alt_domains,
       a_old.access_mode,
       '' as site_secret,  -- 站点级密钥暂为空
       a_old.sdk_version,
       a_old.gateway_url,
       a_old.is_active,
       a_old.clock_stats_enabled,
       a_old.log_retention_days,
       a_old.remark,
       a_old.created_at,
       a_old.updated_at
   FROM biz_application a_old
   JOIN biz_application_new a_new ON CONCAT('app_', SUBSTRING(a_old.site_id, 6)) = a_new.app_key;
   ```

3. **建立映射表**（用于后续数据关联）
   ```sql
   CREATE TABLE _migration_app_site_mapping (
       old_application_id BIGINT,
       new_app_id BIGINT,
       new_site_id BIGINT,
       PRIMARY KEY (old_application_id)
   );
   
   INSERT INTO _migration_app_site_mapping
   SELECT a_old.id, a_new.id, s.id
   FROM biz_application a_old
   JOIN biz_application_new a_new ON CONCAT('app_', SUBSTRING(a_old.site_id, 6)) = a_new.app_key
   JOIN biz_site s ON s.site_key = a_old.site_id;
   ```

### 阶段 2：更新关联表

```sql
-- 更新 biz_rule_site
UPDATE biz_rule_site rs
JOIN _migration_app_site_mapping m ON rs.site_id = m.old_application_id
SET rs.site_id = m.new_site_id;

-- 更新 biz_rule_group
UPDATE biz_rule_group rg
JOIN _migration_app_site_mapping m ON rg.site_id = m.old_application_id
SET rg.site_id = m.new_site_id;
```

### 阶段 3：切换表名（需要停机维护）

```sql
-- 备份旧表
RENAME TABLE biz_application TO biz_application_backup;

-- 新表上位
RENAME TABLE biz_application_new TO biz_application;

-- 清理映射表（可选，建议保留一段时间用于回滚）
-- DROP TABLE _migration_app_site_mapping;
```

---

## 🗄️ ClickHouse 表结构更新

### 1. 添加 site_id 列

```sql
-- 为 decision_events 表添加 site_id 列
ALTER TABLE fangyu.decision_events 
ADD COLUMN site_id UInt64 DEFAULT 0 COMMENT '站点ID';

-- 为 decision_traces 表添加 site_id 列
ALTER TABLE fangyu.decision_traces 
ADD COLUMN site_id UInt64 DEFAULT 0 COMMENT '站点ID';
```

### 2. 数据回填

```sql
-- 从映射表回填 site_id
-- 注意：这需要应用层处理，ClickHouse 不支持 JOIN UPDATE
-- 方案：
-- 1. 导出映射关系到 CSV
-- 2. 使用 clickhouse-client 批量 ALTER UPDATE
-- 3. 或者在 worker 消费新事件时携带 site_id
```

### 3. 创建新分区表（推荐方式）

```sql
-- 创建新表结构
CREATE TABLE fangyu.decision_events_v2 (
    event_id String,
    app_id UInt64 COMMENT '应用ID',
    site_id UInt64 COMMENT '站点ID',
    fingerprint String,
    device_id String DEFAULT '',
    ip String,
    ... (其他字段保持不变)
)
ENGINE = ReplacingMergeTree(event_version)
PARTITION BY (toYYYYMM(occurred_at), app_id)  -- 按月和应用分区
ORDER BY (app_id, site_id, occurred_at, event_id)  -- 两级排序
SETTINGS index_granularity = 8192;

-- 数据迁移（后台执行）
INSERT INTO fangyu.decision_events_v2
SELECT 
    event_id,
    app_id,
    0 as site_id,  -- 旧数据暂填充0，后续补充
    ... (其他字段)
FROM fangyu.decision_events;

-- 切换表名
RENAME TABLE fangyu.decision_events TO fangyu.decision_events_backup;
RENAME TABLE fangyu.decision_events_v2 TO fangyu.decision_events;
```

---

## 🔧 后端代码更新

### 1. 模型更新

**新建 `ApplicationModel`**：
```python
# admin-api/src/infrastructure/repositories/models.py
class ApplicationModel(Base, TimestampMixin):
    __tablename__ = "biz_application"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"))
    app_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    sites: Mapped[list["SiteModel"]] = relationship(back_populates="application")
```

**新建 `SiteModel`**：
```python
class SiteModel(Base, TimestampMixin):
    __tablename__ = "biz_site"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("biz_application.id"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(512), nullable=False)
    alt_domains: Mapped[list[str]] = mapped_column(MySQLJSON, default=list)
    access_mode: Mapped[str] = mapped_column(String(16), default="adapter")
    site_secret: Mapped[str] = mapped_column(String(128), default="")
    sdk_version: Mapped[str | None] = mapped_column(String(16))
    gateway_url: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    clock_stats_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    log_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    remark: Mapped[str | None] = mapped_column(Text)
    
    application: Mapped["ApplicationModel"] = relationship(back_populates="sites")
```

### 2. 仓库更新

**新建 `ApplicationRepository`**
**新建 `SiteRepository`**
**更新 `RuleRepository`**（支持 app_id 和 site_id 查询）

### 3. API 接口更新

**新增应用管理 API**：
- `GET /api/v2/applications` - 应用列表
- `POST /api/v2/applications` - 创建应用
- `PUT /api/v2/applications/{id}` - 更新应用
- `DELETE /api/v2/applications/{id}` - 删除应用

**更新站点管理 API**：
- `GET /api/v2/sites` - 站点列表（支持 appId 过滤）
- `GET /api/v2/applications/{appId}/sites` - 应用下的站点
- 其他 CRUD 接口

**更新访问日志 API**：
```python
@router.get("/access-logs")
async def list_access_logs(
    app_id: int | None = Query(default=None, alias="appId"),
    site_id: int | None = Query(default=None, alias="siteId"),
    ...
):
    # 支持应用级和站点级查询
    pass
```

---

## 🎨 前端代码更新

### 1. 类型定义

```typescript
// dashboard-ui/src/types/api/api.d.ts
namespace Api.Fangyu {
  /** 应用（分组） */
  interface Application {
    id: number
    app_key: string
    name: string
    description: string
    owner_user_id: number | null
    is_active: boolean
    created_at: string
    updated_at: string
    site_count?: number  // 站点数量
  }
  
  /** 站点 */
  interface Site {
    id: number
    site_key: string
    app_id: number
    app_name?: string  // 关联查询
    name: string
    domain: string
    alt_domains: string[]
    access_mode: string
    sdk_version: string | null
    gateway_url: string | null
    is_active: boolean
    created_at: string
    updated_at: string
  }
  
  /** 访问日志查询参数（更新） */
  interface AccessLogListParams {
    appId?: number   // 新增：应用级查询
    siteId?: number  // 站点级查询
    page?: number
    pageSize?: number
    ...
  }
}
```

### 2. API 调用

```typescript
// dashboard-ui/src/api/apps.ts
export const fetchGetApplicationList = (params) => 
  request.get<Api.Common.PageResponse<Api.Fangyu.Application>>('/v2/applications', { params })

export const fetchGetSiteList = (params) =>
  request.get<Api.Common.PageResponse<Api.Fangyu.Site>>('/v2/sites', { params })

export const fetchGetApplicationSites = (appId: number, params) =>
  request.get<Api.Common.PageResponse<Api.Fangyu.Site>>(`/v2/applications/${appId}/sites`, { params })
```

### 3. 页面更新

**新增应用管理页面**：
- `dashboard-ui/src/views/fangyu/applications/index.vue` - 应用列表
- `dashboard-ui/src/views/fangyu/applications/modules/app-dialog.vue` - 应用编辑

**更新站点管理页面**：
- 按应用分组显示站点
- 添加应用选择器
- 支持从应用创建站点

**更新访问日志页面**：
- 添加应用选择器
- 支持应用级和站点级查询切换

---

## ⚠️ 风险与注意事项

### 高风险操作

1. **表结构重命名**（需停机维护）
   - 风险：服务中断
   - 缓解：选择低峰期，提前通知用户

2. **ClickHouse 数据迁移**
   - 风险：大量数据迁移耗时长
   - 缓解：后台异步执行，保留旧表

3. **外键关联更新**
   - 风险：数据不一致
   - 缓解：使用事务，充分测试

### 兼容性问题

1. **旧的 API 调用**
   - 方案：保留兼容层，逐步迁移

2. **客户端认证**
   - 方案：同时支持 `site_key` 和新的认证方式

3. **Redis 缓存键**
   - 方案：更新缓存键格式，清理旧缓存

---

## 📅 迁移时间表

### 阶段划分

| 阶段 | 内容 | 预计时间 | 风险等级 |
|------|------|----------|---------|
| **准备阶段** | 代码开发、测试 | 2-3天 | 低 |
| **灰度测试** | 测试环境验证 | 1天 | 低 |
| **数据迁移** | 生产环境迁移 | 4-6小时 | 中 |
| **服务切换** | 停机维护、切换 | 1-2小时 | 高 |
| **监控观察** | 功能验证、回滚准备 | 1-2天 | 中 |

### 回滚方案

```sql
-- 如果迁移失败，可以回滚
RENAME TABLE biz_application TO biz_application_failed;
RENAME TABLE biz_application_backup TO biz_application;
DROP TABLE biz_site;
```

---

## ✅ 验证清单

### 数据完整性验证

- [ ] 应用数量 = 原 Application 数量
- [ ] 站点数量 = 原 Application 数量
- [ ] 所有站点都正确关联到应用
- [ ] 规则关联正确迁移
- [ ] 规则组关联正确迁移

### 功能验证

- [ ] 应用管理：增删改查
- [ ] 站点管理：增删改查
- [ ] 规则管理：创建、绑定站点
- [ ] 访问日志：应用级查询
- [ ] 访问日志：站点级查询
- [ ] 客户端认证：site_key 认证

### 性能验证

- [ ] ClickHouse 查询性能（应用级）
- [ ] ClickHouse 查询性能（站点级）
- [ ] API 响应时间
- [ ] 前端页面加载速度

---

## 📚 相关文档

- [app_id 设计说明](./app-id-design.md)
- [访问日志字段检查](./access-log-fields-check.md)
- [数据库架构图](./database-schema.md)（待补充）

---

## 🎯 迁移后的优势

1. ✅ **支持企业多站点管理**
2. ✅ **规则可以应用级和站点级管理**
3. ✅ **数据查询支持多级聚合**
4. ✅ **权限管理更灵活**
5. ✅ **为未来扩展打好基础**
