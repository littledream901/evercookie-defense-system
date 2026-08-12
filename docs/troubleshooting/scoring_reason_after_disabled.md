# 关闭风险评分后访问日志仍显示评分原因的问题

## 问题描述

在后台管理界面关闭风险评分功能后，访问日志中仍然显示 `datacenter.new_device` 等评分器原因。

## 原因分析

### 1. 评分原因的来源

访问日志中的 `reason` 字段由多个评分器的原因组成：

- `datacenter` 来自 **ProxyScorer** - 检测到 IP 来自数据中心
- `new_device` 来自 **DeviceScorer** - 检测到新设备（首次访问）

这些原因通过 `;` 连接，例如：`datacenter;new_device` 或前端显示为 `datacenter.new_device`

### 2. 关闭风险评分的实际行为

查看代码 `gateway-api/src/application/services/decision_service.py:850-861`：

```python
if scoring_cfg is not None and not scoring_cfg.enabled:
    # 评分已关闭：跳过此阶段，直接交给默认处置链
    stages.append(
        PipelineStageResult(
            stage=PipelineStage.RISK_SCORING,
            disposition=rule_set.default_disposition or allow(),
            reason="scoring_disabled",
            matched=False,
        )
    )
    resolved = DispositionResolver.fallback(rule_set.default_disposition)
    return self._finalize(resolved, stages, shadow_hits=shadow_hits)
```

**当评分关闭时**：
- 评分阶段被跳过
- `reason` 被设置为 `"scoring_disabled"`
- 不会执行评分器，因此**不应该**出现 `datacenter.new_device` 这样的评分器原因

### 3. 可能的原因

如果您在关闭风险评分后仍看到评分器原因，可能是以下情况之一：

#### 情况 A：查看的是历史数据
- 访问日志中显示的是**关闭评分之前**产生的记录
- 这些日志在评分关闭前就已经写入 ClickHouse
- **解决方法**：刷新页面，查看最新的访问日志

#### 情况 B：配置未生效
- 评分配置缓存有 30 秒 TTL（见 `scoring_config_cache.py:29`）
- 在后台保存"关闭评分"后，需要等待最多 30 秒才能生效
- **解决方法**：等待 30 秒后再测试

#### 情况 C：Redis 缓存问题
- `ScoringConfigCache` 从 Redis 读取配置（键格式：`fangyu:scoring:{site_id}`）
- 如果 Redis 不可用或配置未写入，会回退到默认值（评分开启）
- **解决方法**：检查 Redis 连接和配置是否正确写入

#### 情况 D：查看错误的站点
- 评分配置是**按站点（site_id）维度**的
- 您可能关闭了站点 A 的评分，但查看的是站点 B 的日志
- **解决方法**：确认查看的日志与配置的站点 ID 一致

## 验证步骤

### 1. 检查配置是否生效

在 Redis 中查询评分配置：

```bash
redis-cli
GET fangyu:scoring:{your_site_id}
```

应该看到：
```json
{
  "enabled": false,
  "thresholdSuspect": 30,
  "thresholdHostile": 75,
  ...
}
```

### 2. 检查访问日志的时间戳

- 对比日志的 `event_ts` 时间戳与您关闭评分的时间
- 如果日志时间早于配置变更时间，说明是历史数据

### 3. 触发新请求测试

关闭评分并等待 30 秒后：
1. 触发一次新的访问请求
2. 在访问日志中查找这条最新记录
3. 检查 `reason` 字段是否为 `scoring_disabled`
4. 检查 `decided_stage` 是否跳过了 `risk_scoring`

## 预期行为

**评分关闭后的新日志应该显示：**

| 字段 | 预期值 |
|------|--------|
| `reason` | `scoring_disabled` 或默认处置的原因 |
| `decided_stage` | `decision_rule` 或 `default`（跳过 `risk_scoring`） |
| `score` | `0.0` 或 `null` |
| `scorer_scores` | 空对象 `{}` |

**不应该出现：**
- ❌ `datacenter`、`new_device`、`vpn` 等评分器原因
- ❌ `decided_stage` 为 `risk_scoring`
- ❌ 非零的风险评分

## 相关代码位置

- 评分配置缓存：`gateway-api/src/infrastructure/cache/scoring_config_cache.py`
- 决策流水线：`gateway-api/src/application/services/decision_service.py:843-891`
- 评分器定义：`gateway-api/src/domain/risk/scorers.py`
  - ProxyScorer：第101-140行
  - DeviceScorer：第210-242行

## 总结

如果关闭风险评分后仍看到评分器原因，**最可能的原因是查看的是历史数据**。请：

1. ✅ 刷新访问日志页面
2. ✅ 等待 30 秒让配置生效
3. ✅ 触发新请求并查看最新日志
4. ✅ 检查 Redis 中的配置是否正确

如果按上述步骤操作后问题仍然存在，请检查：
- 站点 ID 是否正确
- Redis 连接是否正常
- 网关服务是否已重启（不应该需要，但可以尝试）
