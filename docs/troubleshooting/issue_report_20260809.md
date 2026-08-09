# 问题排查报告 - 2026-08-09

## 问题 1：规则条件命中明细展开无数据

### 现象
访问日志详情抽屉中，切换到「决策链路」Tab，展开「规则条件命中明细」后显示「该请求无规则条件明细，或数据已过期（保留期 7 天）」。

### 排查结果

**✅ 根本原因已找到：环境变量配置错误**

网关配置类使用 `env_prefix="GATEWAY_"`，字段名为 `decision_trace_sample_rate`，因此正确的环境变量名应该是：
- **正确**：`GATEWAY_DECISION_TRACE_SAMPLE_RATE`
- **错误**：`GATEWAY_TRACE_SAMPLE_RATE`（缺少 `DECISION_` 部分）

由于环境变量名错误，Pydantic Settings 无法读取到配置值，导致网关使用代码中的默认值 `0.01`（1% 采样率）。

**采样逻辑**：
- `should_trace()` 函数：
  - `verdict=trusted` 的请求按 `decision_trace_sample_rate` 采样（默认 1%）
  - `verdict != trusted`（可疑/敌对）的请求 **100% 留痕**，不受采样率影响
- 如果测试的是 `verdict=trusted` 的请求，只有 1% 的概率会记录 traces

**已修复**：
1. ✅ `docker-compose.yml`：将 `GATEWAY_TRACE_SAMPLE_RATE` 改为 `GATEWAY_DECISION_TRACE_SAMPLE_RATE`
2. ✅ `deploy/docker-compose.prod.yml`：将环境变量名修正为带 `GATEWAY_` 前缀的形式

**其他检查结果（✅ 无问题）**：
1. ✅ 网关配置：`decision_trace_enabled: bool = True`（默认开启）
2. ✅ 网关逻辑：正确调用 `collect_condition_traces()` 并附加到 `DecisionEvent`
3. ✅ Worker 配置：`trace_enabled: bool = True`（默认开启）
4. ✅ Worker 逻辑：正确从事件中提取 `conditionTraces` 并写入 ClickHouse `decision_traces` 表
5. ✅ ClickHouse 表结构：正确创建，TTL 7 天
6. ✅ Admin API 查询：正确查询 `decision_traces` 表
7. ✅ 前端请求：正确调用 `/api/v2/access-logs/{request_id}/traces`

### 验证步骤
修复后需要重启 gateway-api 容器使配置生效：
```bash
docker-compose restart gateway-api
# 或生产环境
cd deploy && docker-compose restart gateway-api
```

重启后验证：
1. 使用最近（7 天内）的请求测试
2. 开发环境现在会 100% 记录所有请求的 traces（包括 trusted）
3. 生产环境会 100% 记录可疑/敌对请求，trusted 请求按 10% 采样

---

## 问题 2：评分配置页面逻辑检查

### 检查结果

**后端逻辑（✅ 无问题）**：
- Schema 定义正确：`enabled: bool = True`
- 服务层正确接收并存储 `enabled` 字段
- 同步到 Redis 的逻辑正确

**前端逻辑（✅ 已优化）**：
- ✅ `enabled=false` 时跳过权重校验（第 523 行）
- ✅ 启用评分时强制校验处置策略（第 543-551 行）
- ✅ 确认弹窗根据 `enabled` 状态显示不同文案（第 563-565 行）
- ✅ 已新增阈值合理性校验（第 536-539 行）

**新增校验逻辑**：
1. **阈值合理性**：确保 `threshold_suspect < threshold_hostile`，否则可疑区间为空
2. **权重异常检测**：检查是否所有维度权重都是负数，避免评分异常偏低

### 结论
评分配置页面逻辑完整，已优化阈值合理性校验。

---

## 问题 3：威胁情报页面是否需要拆分

### 现状分析

**当前页面结构**（6 个 Tab）：

| Tab 名称 | 数据类型 | 用途 | 规则条件引用 |
|---------|---------|------|-------------|
| IP 威胁 | 威胁情报（黑名单） | 恶意 IP，带风险分 | `intel.*` |
| ASN 情报 | 威胁情报（黑名单） | 高风险 ASN，带风险分 | `intel.*` |
| 爬虫特征 | 威胁情报（黑名单） | UA/IP 匹配规则，带风险分 | `intel.*` |
| 指纹情报 | 威胁情报（黑名单） | 设备指纹黑名单，带风险分 | `intel.*` |
| IP 画像 | 网络画像（辅助） | IP 网络属性标注 | `ip.*` |
| GeoIP 录入 | 网络画像（辅助） | IP 归属地修正 | `ip.*` |

**潜在混淆点**：
1. 页面标题「威胁情报」包含两类不同性质的数据
2. 用户在规则条件中看到 `intel.*` 字段时，可能误以为是指整个页面的数据
3. IP 画像和 GeoIP 数据是辅助画像，不是真正的威胁情报

### 解决方案

**✅ 建议：不拆分页面，优化文案说明**

理由：
1. 拆分成本高（新路由、新页面、调整菜单、迁移权限码）
2. 6 类情报功能关联性强，统一管理更便于维护
3. 真正的问题是命名和说明不清晰，而非页面组织问题

**已实施的优化**：
1. ✅ 页面顶部已添加说明区块，明确区分两类数据及其引用方式
2. ✅ 字段定义中已有详细注释：
   - `IP_FIELDS` 注释：「其中代理/VPN/数据中心等网络属性部分来自『情报与画像 - IP 画像』的人工标注」
   - `INTEL_FIELDS` 注释：「由网关查询后台维护的四类黑名单情报得出...注意：IP 画像和 GeoIP 录入属于『网络画像』数据，通过 ip.* 字段族引用，不在此处」

### 结论
当前文案已足够清晰，无需拆分页面。用户可通过页面顶部说明和字段定义注释理解两类数据的区别。

---

## 总结

| 问题 | 状态 | 修复措施 |
|-----|------|---------|
| 规则条件命中明细无数据 | ✅ 已修复 | 修正环境变量名称，重启网关生效 |
| 评分配置页面逻辑 | ✅ 已优化 | 新增阈值合理性校验 |
| 威胁情报页面拆分 | ✅ 无需拆分 | 文案已清晰，无需改动 |

---

## 下一步行动

1. **立即执行**：重启 gateway-api 容器使配置修复生效
   ```bash
   docker-compose restart gateway-api
   ```

2. **验证测试**：使用最近（7 天内）的请求测试 traces 功能，优先选择被拦截的请求（verdict=hostile/suspicious）

3. **长期优化建议**：
   - 在访问日志列表页增加「是否有 traces」标识，方便用户快速定位可查看明细的请求
   - 考虑在后台增加「trace 统计」页面，显示当前 traces 数据量、采样率效果等指标
