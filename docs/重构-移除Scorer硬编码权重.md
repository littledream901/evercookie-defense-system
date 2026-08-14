# 重构：移除 Scorer 硬编码权重

## 问题背景

用户发现系统存在**双重权重机制**：

1. **Scorer 类的硬编码权重**：每个 Scorer 类上定义了 `weight` 属性（如 `weight = 1.2`, `weight = 0.8`）
2. **评分配置的权重覆盖**：后台可以通过评分配置系统调整每个维度的权重

这两套机制造成了混乱：
- 用户不清楚最终生效的是哪个权重
- 硬编码的默认权重无法通过配置修改
- 配置系统的权重需要"覆盖"硬编码值，增加了理解成本

## 用户质疑

> "不是已经有一个评分配置了吗，为什么不能只用评分配置？"
> "这是一个多余的控制，在评分配置中可以显式配置，为什么还要有这个多余的机制？"

**用户说得对。** Scorer 类上的硬编码权重完全是多余的，应该删除。

## 解决方案

### 改动 1：移除 Scorer 类的 weight 属性

删除所有 Scorer 子类的 `weight` 类属性，统一在 `score()` 方法返回时使用 `weight=1.0`。

**修改文件**：`gateway-api/src/domain/risk/scorers.py`

```python
# ❌ 修改前
class IpReputationScorer(RiskScorer):
    name = "ip_reputation"
    weight = 1.2  # ← 硬编码权重

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        ...
        return ScorerOutput(..., weight=self.weight)

# ✅ 修改后
class IpReputationScorer(RiskScorer):
    name = "ip_reputation"  # ← 移除 weight 属性

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        ...
        return ScorerOutput(..., weight=1.0)  # ← 统一使用 1.0
```

**受影响的 Scorer**：
- `IpReputationScorer`: `weight = 1.2` → 移除
- `ProxyScorer`: `weight = 1.5` → 移除
- `UserAgentScorer`: `weight = 0.8` → 移除
- `DeviceScorer`: `weight = 1.0` → 移除
- `BehaviorScorer`: `weight = 1.0` → 移除
- `InteractionScorer`: `weight = 0.8` → 移除
- `IntelScorer`: `weight = 1.0` → 移除

### 改动 2：统一后台配置的默认权重

**修改文件**：`admin-api/src/application/services/scoring_service.py`

将 `SCORING_DIMENSIONS` 中所有维度的 `defaultWeight` 统一设为 `10`（对应 scorer 权重 1.0）：

```python
# 修改前（不一致的默认权重）
"ip_reputation": defaultWeight: 12,
"proxy": defaultWeight: 15,
"user_agent": defaultWeight: 8,
"interaction": defaultWeight: 8,

# 修改后（统一的默认权重）
所有维度: defaultWeight: 10
```

**说明**：
- `defaultWeight` 是前端滑块的初始位置（整数量纲）
- 网关侧会除以 10 还原为浮点权重（10 → 1.0）
- 统一设为 10 表示所有维度默认等权重，由用户按需调整

### 改动 3：更新配置文档注释

修改 `SCORING_DIMENSIONS` 的文档字符串，明确说明：
- `key` 必须与 `RiskScorer.name` 严格一致
- `defaultWeight` 是前端展示的初始值，不参与后端计算
- 所有维度默认等权重（1.0），避免隐含的优先级假设

## 权重机制说明

### 最终权重的决定流程

```
1. Scorer 返回 ScorerOutput(weight=1.0)  ← 固定基准权重
2. RiskPipeline.run(weights={...})        ← 评分配置传入
3. output.with_weight(override)           ← 应用配置覆盖
4. 最终权重 = 配置值（或 1.0）
```

### 配置示例

```python
# 后台评分配置
{
  "weights": {
    "proxy": 20,        # 20 / 10 = 2.0，提高代理检测权重
    "user_agent": 5,    # 5 / 10 = 0.5，降低 UA 检测权重
    "ip_reputation": 0  # 0 / 10 = 0.0，关闭 IP 信誉检测
  }
}

# 未配置的维度自动使用 1.0
# 例如：device、behavior、interaction、intel 都使用 1.0
```

## 优势

1. **单一配置来源**：权重只从评分配置系统获取，不存在"覆盖"的概念
2. **简化理解成本**：用户只需关注后台配置页面，不需要阅读代码
3. **消除歧义**：不再有"默认权重 vs 配置权重"的混淆
4. **等权重起点**：所有维度默认权重为 1.0，体现公平性，避免隐含偏好

## 兼容性

### 向后兼容

- ✅ 现有的评分配置数据无需迁移
- ✅ 未配置权重的站点自动使用 1.0（等权重）
- ✅ 已配置权重的站点继续生效

### 行为变化

**对于未配置评分权重的站点**：

| 维度 | 旧权重 | 新权重 | 影响 |
|-----|--------|--------|------|
| ip_reputation | 1.2 | 1.0 | 分数贡献减少 16.7% |
| proxy | 1.5 | 1.0 | 分数贡献减少 33.3% |
| user_agent | 0.8 | 1.0 | 分数贡献增加 25% |
| interaction | 0.8 | 1.0 | 分数贡献增加 25% |
| device | 1.0 | 1.0 | 无变化 |
| behavior | 1.0 | 1.0 | 无变化 |
| intel | 1.0 | 1.0 | 无变化 |

**建议**：
- 如果线上站点依赖旧的权重分布，应在后台显式配置权重（保持原有行为）
- 新站点直接使用等权重（1.0），然后根据实际效果调整

## 文件清单

### 修改的文件

1. `gateway-api/src/domain/risk/scorers.py`
   - 移除所有 Scorer 的 `weight` 类属性
   - 统一返回 `weight=1.0`

2. `admin-api/src/application/services/scoring_service.py`
   - 统一 `defaultWeight` 为 10
   - 更新文档注释

### 相关文件（无需修改）

- `gateway-api/src/domain/risk/pipeline.py`：权重覆盖逻辑无需修改
- `gateway-api/src/infrastructure/cache/scoring_config_cache.py`：配置加载逻辑无需修改
- 前端评分配置页面：无需修改（继续使用滑块调整权重）

## 测试建议

1. **验证默认行为**：创建新站点，不配置权重，验证所有维度使用 1.0
2. **验证配置覆盖**：配置部分维度权重，验证未配置的维度使用 1.0
3. **验证权重 0**：设置某个维度权重为 0，验证该维度不参与评分
4. **回归测试**：对比修改前后的评分结果，确认行为变化符合预期

## 总结

这次重构彻底移除了 Scorer 类的硬编码权重，实现了**单一配置来源**的设计原则：

- 所有权重配置统一由**评分配置系统**管理
- Scorer 代码中只保留基准权重 1.0
- 用户通过后台配置页面调整权重，无需修改代码

这符合"配置与代码分离"的最佳实践，降低了系统的复杂度和维护成本。
