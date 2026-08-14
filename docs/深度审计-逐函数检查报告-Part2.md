# 深度审计：逐函数检查报告（续）

## 第二部分：Risk 评分模块

### 8. `RiskPipeline.run()` ⚠️ 发现问题

**位置**: `gateway-api/src/domain/risk/pipeline.py:76-129`

```python
def run(
    self,
    snapshot: ProfileSnapshot,
    *,
    challenge_threshold: float | None = None,
    block_threshold: float | None = None,
    weights: dict[str, float] | None = None,
    disposition_suspect: Disposition | None = None,
    disposition_hostile: Disposition | None = None,
) -> RiskDecision:
    overrides = weights or {}
    
    outputs: list[ScorerOutput] = []
    for scorer in self._scorers:
        output = scorer.score(snapshot)  # ⚠️ 问题点 1
        override = overrides.get(output.name)
        if override is not None:  # ⚠️ 问题点 2
            output = output.with_weight(override)
        outputs.append(output)
    
    weighted_sum = sum(o.weighted_score for o in outputs if o.applies)
    final_score = round(max(0.0, min(100.0, weighted_sum)), 2)  # ⚠️ 问题点 3
```

#### 审计结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 输入验证 | ⚠️ | 未验证 snapshot 非 None |
| 类型安全 | ⚠️ | scorer.score() 可能抛异常 |
| 边界条件 | ⚠️ | weights 可能包含负值 |
| 空值处理 | ✅ | 正确处理 None |
| 异常处理 | ❌ | scorer 异常会中断整个流水线 |
| 数值溢出 | ⚠️ | weighted_sum 可能无限大 |
| 逻辑正确性 | ✅ | 核心逻辑正确 |

#### 发现的问题

**问题 1**: Scorer 异常未捕获

```python
# 如果某个 scorer.score() 抛异常，整个评分流程崩溃
for scorer in self._scorers:
    output = scorer.score(snapshot)  # 可能抛异常
```

**问题 2**: weights 可能包含负值或无效值

```python
# 后台配置可能被篡改
weights = {"ip_reputation": -1.0}  # 负权重
weights = {"ip_reputation": float('inf')}  # 无穷大
weights = {"ip_reputation": float('nan')}  # NaN
```

**问题 3**: weighted_sum 可能产生 NaN

```python
# 如果某个 scorer 返回 NaN 分数
weighted_sum = sum([1.0, float('nan'), 3.0])  # = nan
final_score = round(max(0.0, min(100.0, nan)), 2)  # = nan
```

#### 建议修复

```python
def run(
    self,
    snapshot: ProfileSnapshot,
    *,
    challenge_threshold: float | None = None,
    block_threshold: float | None = None,
    weights: dict[str, float] | None = None,
    disposition_suspect: Disposition | None = None,
    disposition_hostile: Disposition | None = None,
) -> RiskDecision:
    """执行全部 scorer 并累加加权分。"""
    
    # 输入验证
    if snapshot is None:
        raise ValueError("snapshot 不能为 None")
    
    overrides = weights or {}
    
    # 验证 weights 有效性
    validated_overrides: dict[str, float] = {}
    for name, weight in overrides.items():
        if not isinstance(weight, (int, float)):
            _logger.warning("risk_invalid_weight_type", scorer=name, weight=weight)
            continue
        if math.isnan(weight) or math.isinf(weight):
            _logger.warning("risk_invalid_weight_value", scorer=name, weight=weight)
            continue
        if weight < 0:
            _logger.warning("risk_negative_weight", scorer=name, weight=weight)
            weight = 0.0
        validated_overrides[name] = weight
    
    outputs: list[ScorerOutput] = []
    for scorer in self._scorers:
        try:
            output = scorer.score(snapshot)
            
            # 验证 scorer 输出
            if math.isnan(output.score) or math.isinf(output.score):
                _logger.error(
                    "risk_scorer_invalid_score",
                    scorer=scorer.name,
                    score=output.score
                )
                output = ScorerOutput(
                    name=scorer.name,
                    score=0.0,
                    reason="invalid_score",
                    weight=scorer.weight,
                    applies=False
                )
            
            # 应用权重覆盖
            override = validated_overrides.get(output.name)
            if override is not None:
                output = output.with_weight(override)
            
            outputs.append(output)
        except Exception as exc:
            _logger.error(
                "risk_scorer_failed",
                scorer=scorer.name,
                error=str(exc),
                exc_info=True
            )
            # 失败的 scorer 不参与评分
            outputs.append(ScorerOutput(
                name=scorer.name,
                score=0.0,
                reason=f"scorer_error:{type(exc).__name__}",
                weight=scorer.weight,
                applies=False
            ))
    
    # 只累加有效的分数
    valid_scores = [
        o.weighted_score 
        for o in outputs 
        if o.applies and not math.isnan(o.weighted_score) and not math.isinf(o.weighted_score)
    ]
    
    weighted_sum = sum(valid_scores) if valid_scores else 0.0
    
    # 确保 final_score 在有效范围内
    if math.isnan(weighted_sum) or math.isinf(weighted_sum):
        _logger.error("risk_invalid_weighted_sum", weighted_sum=weighted_sum)
        weighted_sum = 0.0
    
    final_score = round(max(0.0, min(100.0, weighted_sum)), 2)
    reasons = [o.reason for o in outputs if o.applies and o.reason]
    
    c_threshold = challenge_threshold if challenge_threshold is not None else self._challenge_threshold
    b_threshold = block_threshold if block_threshold is not None else self._block_threshold
    
    return RiskDecision(
        score=final_score,
        disposition=self._decide(
            final_score, 
            c_threshold, 
            b_threshold,
            disposition_suspect,
            disposition_hostile,
        ),
        reasons=reasons,
        per_scorer=outputs,
    )
```

---

### 9. `RiskPipeline._decide()` ⚠️ 阈值验证不足

**位置**: `gateway-api/src/domain/risk/pipeline.py:131-156`

```python
def _decide(
    self,
    score: float,
    challenge_threshold: float | None = None,
    block_threshold: float | None = None,
    disposition_suspect: Disposition | None = None,
    disposition_hostile: Disposition | None = None,
) -> Disposition:
    ct = challenge_threshold if challenge_threshold is not None else self._challenge_threshold
    bt = block_threshold if block_threshold is not None else self._block_threshold
    
    # 评分 → Verdict 判断
    if score >= bt:  # ⚠️ 问题点 1
        return disposition_hostile or deny()
    if score >= ct:  # ⚠️ 问题点 2
        return disposition_suspect or challenge(ChallengeKind.CAPTCHA)
    return allow()
```

#### 审计结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 输入验证 | ⚠️ | 未验证阈值有效性 |
| 类型安全 | ⚠️ | score 可能是 NaN |
| 边界条件 | ⚠️ | 阈值可能颠倒 |
| 空值处理 | ✅ | 正确处理 None |
| 异常处理 | ✅ | 无异常风险 |
| 逻辑正确性 | ⚠️ | 阈值顺序未验证 |

#### 发现的问题

**问题 1**: 阈值可能为 NaN 或无穷大

```python
# 配置错误
_decide(50.0, challenge_threshold=float('nan'), block_threshold=75.0)
# NaN 参与比较的结果是 False
# score >= nan → False，永远走到最后的 allow()
```

**问题 2**: 阈值可能颠倒

```python
# 配置错误：挑战阈值 > 拦截阈值
_decide(60.0, challenge_threshold=80.0, block_threshold=50.0)
# score=60 >= bt=50 → 拦截 ✅
# 但语义上 challenge_threshold 应该 < block_threshold
```

**问题 3**: score 可能是 NaN

```python
_decide(float('nan'), challenge_threshold=30.0, block_threshold=75.0)
# nan >= 75 → False
# nan >= 30 → False
# 返回 allow() - NaN 分数被放行！
```

#### 建议修复

```python
def _decide(
    self,
    score: float,
    challenge_threshold: float | None = None,
    block_threshold: float | None = None,
    disposition_suspect: Disposition | None = None,
    disposition_hostile: Disposition | None = None,
) -> Disposition:
    """基于评分判断 Verdict。"""
    
    # 验证 score 有效性
    if math.isnan(score) or math.isinf(score):
        _logger.error("risk_decide_invalid_score", score=score)
        # NaN/Inf 分数视为高风险
        return disposition_hostile or deny()
    
    # 获取并验证阈值
    ct = challenge_threshold if challenge_threshold is not None else self._challenge_threshold
    bt = block_threshold if block_threshold is not None else self._block_threshold
    
    # 验证阈值有效性
    if math.isnan(ct) or math.isinf(ct) or ct < 0 or ct > 100:
        _logger.error("risk_invalid_challenge_threshold", threshold=ct)
        ct = 30.0  # 回退到默认值
    
    if math.isnan(bt) or math.isinf(bt) or bt < 0 or bt > 100:
        _logger.error("risk_invalid_block_threshold", threshold=bt)
        bt = 75.0  # 回退到默认值
    
    # 验证阈值顺序
    if ct > bt:
        _logger.warning(
            "risk_threshold_inverted",
            challenge=ct,
            block=bt
        )
        # 交换阈值或使用默认值
        ct, bt = min(ct, bt), max(ct, bt)
    
    # 评分 → Verdict 判断
    if score >= bt:
        return disposition_hostile or deny()
    if score >= ct:
        return disposition_suspect or challenge(ChallengeKind.CAPTCHA)
    return allow()
```

---

### 10. `ScorerOutput.with_weight()` ✅ 正确，可优化

**位置**: `gateway-api/src/domain/risk/scorers.py:41-49`

```python
def with_weight(self, weight: float) -> ScorerOutput:
    """返回替换权重后的副本。"""
    return ScorerOutput(
        name=self.name,
        score=self.score,
        reason=self.reason,
        weight=weight,  # ⚠️ 未验证
        applies=self.applies,
    )
```

#### 审计结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 输入验证 | ⚠️ | 未验证 weight 有效性 |
| 类型安全 | ✅ | 类型注解明确 |
| 边界条件 | ⚠️ | weight 可能为负或 NaN |
| 逻辑正确性 | ✅ | 正确 |

#### 建议优化

```python
def with_weight(self, weight: float) -> ScorerOutput:
    """返回替换权重后的副本。"""
    # 验证权重
    if math.isnan(weight) or math.isinf(weight):
        from fangyu_shared.logging import get_logger
        _logger = get_logger("risk")
        _logger.warning("scorer_invalid_weight", scorer=self.name, weight=weight)
        weight = 0.0
    
    if weight < 0:
        from fangyu_shared.logging import get_logger
        _logger = get_logger("risk")
        _logger.warning("scorer_negative_weight", scorer=self.name, weight=weight)
        weight = 0.0
    
    return ScorerOutput(
        name=self.name,
        score=self.score,
        reason=self.reason,
        weight=weight,
        applies=self.applies,
    )
```

---

### 11. `IpReputationScorer.score()` ✅ 正确

**位置**: `gateway-api/src/domain/risk/scorers.py:77-84`

```python
def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
    ip = snapshot.ip
    if not ip.has_reputation:
        return self._skip("no_reputation_data")
    reputation = ip.reputation_score
    score = max(0.0, 100.0 - reputation)  # ✅ 正确：确保非负
    reason = f"ip_reputation={reputation:.1f}" if score > 30 else None
    return ScorerOutput(name=self.name, score=score, reason=reason, weight=self.weight)
```

#### 审计结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 输入验证 | ✅ | 检查 has_reputation |
| 类型安全 | ✅ | 类型安全 |
| 边界条件 | ✅ | 使用 max() 确保非负 |
| 空值处理 | ✅ | 正确跳过 |
| 逻辑正确性 | ✅ | 完全正确 |

#### 潜在边界问题

```python
# 如果 reputation_score 是负数或 > 100？
reputation = -10  # score = max(0, 100 - (-10)) = 110 ⚠️
reputation = 150  # score = max(0, 100 - 150) = 0 ✅
```

#### 建议优化

```python
def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
    ip = snapshot.ip
    if not ip.has_reputation:
        return self._skip("no_reputation_data")
    
    reputation = ip.reputation_score
    
    # 确保 reputation 在有效范围内
    if math.isnan(reputation) or math.isinf(reputation):
        return self._skip("invalid_reputation_value")
    
    # reputation 应该在 [0, 100] 范围内，但做防御性处理
    reputation = max(0.0, min(100.0, reputation))
    
    score = max(0.0, min(100.0, 100.0 - reputation))
    reason = f"ip_reputation={reputation:.1f}" if score > 30 else None
    return ScorerOutput(name=self.name, score=score, reason=reason, weight=self.weight)
```

---

## 总结：Risk 模块发现的问题

### 🔴 严重问题 (需要立即修复)

1. **`run()` Scorer 异常未捕获** - 单个 scorer 崩溃会导致整个评分失败
2. **`_decide()` NaN 分数被放行** - NaN 分数会绕过所有判断

### ⚠️ 中等问题 (建议修复)

3. **`run()` 权重验证不足** - 负值/NaN/Inf 权重可能导致错误结果
4. **`_decide()` 阈值验证不足** - 颠倒/无效的阈值可能导致错误判断
5. **`with_weight()` 权重验证不足** - 同上

### ✅ 轻微问题 (可选优化)

6. **`IpReputationScorer` 边界处理** - reputation 可能超出 [0, 100] 范围

---

## 进度总结

- ✅ Clock 模块审计完成 - 发现 4 个问题
- ✅ Risk 模块审计完成 - 发现 6 个问题
- ⏳ Rule 模块待审计
- ⏳ 操作符模块待审计
- ⏳ 决策服务主流程待审计

