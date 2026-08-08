# 访问日志字段完整性检查

## 字段对比表

| 字段名 | 后端 ClickHouse | 前端类型定义 | 页面显示 | 状态 | 说明 |
|--------|----------------|-------------|----------|------|------|
| **基础信息** |
| `event_id` | ✅ | ❌ | ❌ | ⚠️ 技术字段 | 事件唯一标识（内部使用） |
| `app_id` | ✅ | ❌ | ❌ | ⚠️ 技术字段 | 站点 ID（查询参数已有 siteId） |
| `request_id` | ✅ | ✅ | ✅ | ✅ 完整 | 请求唯一标识 |
| `fingerprint` | ✅ | ✅ | ❌ | ⚠️ 部分 | 设备指纹（未在列表显示） |
| `fingerprint_is_derived` | ✅ | ✅ | ❌ | ✅ 已同步 | 指纹是否为服务端派生 |
| `device_id` | ✅ | ✅ | ✅ | ✅ 完整 | 设备 ID（显示前 8 位） |
| `ingress` | ✅ | ✅ | ❌ | ✅ 已同步 | 接入来源（sdk/adapter） |
| `occurred_at` | ✅ | ✅ | ✅ | ✅ 完整 | 发生时间 |
| `schema_version` | ✅ | ❌ | ❌ | ⚠️ 技术字段 | 事件协议版本 |
| `event_version` | ✅ | ❌ | ❌ | ⚠️ 技术字段 | 事件版本号 |
| **网络信息** |
| `ip` | ✅ | ✅ | ✅ | ✅ 完整 | IP 地址 |
| `ip_type` | ✅ | ✅ | ✅ | ✅ 完整 | IP 类型（ipv4/ipv6，tooltip 显示） |
| `country` | ✅ | ✅ | ✅ | ✅ 完整 | 国家代码 |
| `asn` | ✅ | ✅ | ✅ | ✅ 完整 | ASN 号 |
| `asn_org` | ✅ | ✅ | ✅ | ✅ 完整 | ASN 组织名 |
| `connection_type` | ✅ | ✅ | ✅ | ✅ 完整 | 连接类型 |
| `is_vpn` | ✅ | ✅ | ✅ | ✅ 完整 | 是否 VPN（tooltip 显示） |
| `is_proxy` | ✅ | ✅ | ✅ | ✅ 完整 | 是否代理（tooltip 显示） |
| **请求信息** |
| `host` | ✅ | ✅ | ✅ | ✅ 完整 | 访问域名 |
| `path` | ✅ | ✅ | ✅ | ✅ 完整 | 访问路径 |
| `referer` | ✅ | ✅ | ✅ | ✅ 完整 | 来路 URL |
| `method` | ✅ | ✅ | ❌ | ✅ 已同步 | HTTP 方法（GET/POST） |
| `user_agent` | ✅ | ✅ | ✅ | ✅ 完整 | User-Agent 原文（tooltip 显示） |
| `accept_language` | ✅ | ✅ | ✅ | ✅ 完整 | 客户端语言偏好 |
| **设备信息** |
| `device_type` | ✅ | ✅ | ✅ | ✅ 完整 | 设备类型 |
| `os_name` | ✅ (os_name) | ✅ (os) | ✅ | ✅ 完整 | 操作系统（后端映射为 os） |
| `browser_name` | ✅ (browser_name) | ✅ (browser) | ✅ | ✅ 完整 | 浏览器（后端映射为 browser） |
| **爬虫识别** |
| `is_bot` | ✅ | ✅ | ✅ | ✅ 完整 | 是否为爬虫 |
| `crawler_name` | ✅ | ✅ | ✅ | ✅ 完整 | 爬虫名称 |
| `crawler_vendor` | ✅ | ✅ | ✅ | ✅ 完整 | 爬虫厂商 |
| `crawler_category` | ✅ | ✅ | ✅ | ✅ 完整 | 爬虫类别 |
| **决策信息** |
| `verdict` | ✅ | ✅ | ✅ | ✅ 完整 | 判决结果 |
| `mechanism` | ✅ | ✅ | ✅ | ✅ 完整 | 处置机制 |
| `target_kind` | ✅ | ✅ | ❌ | ✅ 已同步 | 目标类型 |
| `target_url` | ✅ | ✅ | ❌ | ✅ 已同步 | 目标 URL |
| `http_status` | ✅ | ✅ | ❌ | ⚠️ 部分 | HTTP 状态码（未在列表显示） |
| `decided_by` | ✅ | ✅ | ✅ | ✅ 完整 | 决策来源 |
| `decided_stage` | ✅ (decided_stage) | ✅ (stage) | ❌ | ⚠️ 部分 | 决策阶段（后端映射为 stage，未显示） |
| `decided_rule_id` | ✅ (decided_rule_id) | ✅ (rule_id) | ❌ | ⚠️ 部分 | 决策规则 ID（后端映射为 rule_id，未显示） |
| `reason` | ✅ | ✅ | ✅ | ✅ 完整 | 决策原因 |
| `score` | ✅ | ✅ | ✅ | ✅ 完整 | 风险评分 |
| `scorer_scores` | ✅ | ✅ | ❌ | ⚠️ 部分 | 各评分器分数（未在列表显示） |
| `rule_ids` | ✅ | ✅ | ❌ | ✅ 已同步 | 命中的规则 ID 列表 |
| `decision_cost_ms` | ✅ | ✅ | ✅ | ✅ 完整 | 决策耗时 |
| **追踪信息** |
| `repeat_key` | ✅ | ✅ | ❌ | ⚠️ 部分 | 重复访问键（未在列表显示） |
| `repeat_value` | ✅ | ✅ | ❌ | ⚠️ 部分 | 重复访问值（未在列表显示） |
| `evercookie_restore` | ✅ | ✅ | ❌ | ⚠️ 部分 | Evercookie 恢复标记（未在列表显示） |
| **影子评估** |
| `shadow_rule_ids` | ✅ | ✅ | ❌ | ⚠️ 部分 | 影子规则 ID 列表（未在列表显示） |
| `shadow_verdicts` | ✅ | ✅ | ❌ | ✅ 已同步 | 影子判决结果 |

## 统计汇总

- **后端字段总数**: 47 个
- **前端类型定义**: 37 个（已同步）
- **页面列表显示**: 27 个（核心字段已显示）
- **完全缺失**: 4 个字段（仅技术元数据）
- **部分缺失**: 10 个字段（有定义但未在列表显示）

## 需要修复的字段

### ✅ 已完成同步（2026-08-08）

所有扩展字段已添加到前端类型定义：

1. **`asn_org`** - ASN 组织名 ✅
2. **`method`** - HTTP 方法 ✅
3. **`target_kind` / `target_url`** - 重定向目标信息 ✅
4. **`ingress`** - 接入来源（sdk/adapter）✅
5. **`fingerprint_is_derived`** - 指纹是否派生 ✅
6. **`rule_ids`** - 命中的规则 ID 列表 ✅
7. **`shadow_verdicts`** - 影子判决结果 ✅

### 低优先级（仅技术元数据，未同步）

这些字段为内部技术字段，暂不需要在前端使用：

- **`event_id`** - 事件唯一标识（内部使用）
- **`app_id`** - 站点 ID（查询参数已有 siteId）
- **`schema_version`** - 事件协议版本（内部版本控制）
- **`event_version`** - 事件版本号（ClickHouse ReplacingMergeTree 使用）

## 字段映射说明

后端使用蛇形命名（snake_case），前端使用驼峰命名（camelCase），以下字段有映射：

| 后端字段 | 前端字段 | 映射位置 |
|---------|---------|---------|
| `os_name` | `os` | access_logs.py:20 |
| `browser_name` | `browser` | access_logs.py:21 |
| `decided_stage` | `stage` | access_logs.py:22 |
| `decided_rule_id` | `rule_id` | access_logs.py:23 |

## 建议

1. **立即修复**: 添加 `asn_org` 到前端类型定义
2. **逐步完善**: 在详情抽屉中显示更多字段（如 method、target_url、rule_ids）
3. **保持同步**: 后端新增字段时同步更新前端类型定义
4. **文档化**: 维护字段映射表，避免命名混乱
