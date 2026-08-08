"""风险评分流水线：执行 Scorer，累加加权分并截顶，按阈值产出处置。

为什么是累加截顶而不是加权平均
------------------------------
早期实现用 ``Σ(sᵢ·wᵢ) / Σwᵢ``（加权平均），有两个致命问题：

1. **分母含全部 scorer 权重，与该 scorer 本次是否产出信号无关。**
   对绝大多数请求恒为 0 的 scorer（``behavior`` 只查异常 method 与超长 path）
   变成固定稀释项。实测 sqlmap UA + 数据中心 IP + 全新设备只有 38.8 分，
   低于当时的 40 分挑战线，直接放行。
2. **违反单调性。** 同样的信号，接上一个恒为 0 的 scorer 后总分从 43.0 掉到
   35.2 —— 新增一个 scorer 会让既有请求的分数下降，等于一次隐性的全局阈值变更，
   使得扩展 scorer 变成高风险操作。

现改为 ``min(100, Σ(sᵢ·wᵢ))``：与原版累加语义一致，运维对累加已有直觉，
且「增加正分信号绝不降低总分」天然成立。

权重来源
--------
由评分配置页维护，经 ``ScoringConfigCache`` 下发到 ``run(weights=...)``，
覆盖 scorer 类上的默认权重。缺项沿用默认值，因此后台只需配置关心的维度。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fangyu_shared.schemas.disposition import (
    ChallengeKind,
    Disposition,
    allow,
    challenge,
    deny,
)
from src.domain.profile.builder import ProfileSnapshot
from src.domain.risk.scorers import RiskScorer, ScorerOutput


@dataclass(frozen=True, slots=True)
class RiskDecision:
    score: float
    disposition: Disposition
    reasons: list[str] = field(default_factory=list)
    per_scorer: list[ScorerOutput] = field(default_factory=list)

    @property
    def scorer_scores(self) -> dict[str, float]:
        """各 scorer 的原始分，落库为 ClickHouse Map 供明细下钻。

        旧版把这类明细塞进 String 字段存 JSON，无法在 SQL 里过滤或聚合。
        只收录实际参与判定的 scorer —— 未参与的写 0 会与「判定为 0 分」
        混淆，在 SQL 侧无法区分。
        """
        return {o.name: round(o.score, 2) for o in self.per_scorer if o.applies}

    @property
    def applied_weights(self) -> dict[str, float]:
        """本次生效的权重，供排障回答「为什么是这个分」。"""
        return {o.name: round(o.weight, 3) for o in self.per_scorer if o.applies}


class RiskPipeline:
    """风险评分聚合器。"""

    def __init__(
        self,
        scorers: list[RiskScorer],
        *,
        challenge_threshold: float = 30.0,
        block_threshold: float = 75.0,
    ) -> None:
        self._scorers = scorers
        self._challenge_threshold = challenge_threshold
        self._block_threshold = block_threshold

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
        """执行全部 scorer 并累加加权分。

        Args:
            snapshot: 画像快照。
            challenge_threshold: 动态阈值覆盖，来自 ScoringConfigCache；
                None 时沿用构造时的静态值。
            block_threshold: 同上。
            weights: ``scorer 名 → 权重`` 覆盖表，来自评分配置页。缺项的 scorer
                沿用类上的默认权重，因此后台只配关心的维度即可。
            disposition_suspect: 可疑流量的自定义处置，来自评分配置。
            disposition_hostile: 敌对流量的自定义处置，来自评分配置。
        """
        overrides = weights or {}

        outputs: list[ScorerOutput] = []
        for scorer in self._scorers:
            output = scorer.score(snapshot)
            override = overrides.get(output.name)
            if override is not None:
                output = output.with_weight(override)
            outputs.append(output)

        # 只累加实际参与判定的 scorer。未参与者权重不进分子也不进分母
        # （累加模型没有分母，但语义上仍需排除，避免 applies=False 时
        # scorer 返回的占位分被计入）。
        weighted_sum = sum(o.weighted_score for o in outputs if o.applies)
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

    def _decide(
        self,
        score: float,
        challenge_threshold: float | None = None,
        block_threshold: float | None = None,
        disposition_suspect: Disposition | None = None,
        disposition_hostile: Disposition | None = None,
    ) -> Disposition:
        """基于评分判断 Verdict，然后选择对应的 Mechanism。
        
        核心设计：评分即裁决
        - score → Verdict（基于阈值判断，不可配）
        - Verdict → Mechanism（从配置读取，可配）
        """
        ct = challenge_threshold if challenge_threshold is not None else self._challenge_threshold
        bt = block_threshold if block_threshold is not None else self._block_threshold
        
        # 评分 → Verdict 判断
        if score >= bt:
            # 敌对：使用配置的处置，默认为 deny
            return disposition_hostile or deny()
        if score >= ct:
            # 可疑：使用配置的处置，默认为 challenge
            return disposition_suspect or challenge(ChallengeKind.CAPTCHA)
        # 可信：始终放行
        return allow()
