"""风险评分流水线：执行 Scorer，加权聚合，按阈值产出处置。"""

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
        """
        return {o.name: round(o.score, 2) for o in self.per_scorer}


class RiskPipeline:
    """风险评分聚合器。"""

    def __init__(
        self,
        scorers: list[RiskScorer],
        *,
        challenge_threshold: float = 40.0,
        block_threshold: float = 70.0,
    ) -> None:
        self._scorers = scorers
        self._challenge_threshold = challenge_threshold
        self._block_threshold = block_threshold

    def run(self, snapshot: ProfileSnapshot) -> RiskDecision:
        outputs: list[ScorerOutput] = [scorer.score(snapshot) for scorer in self._scorers]
        total_weight = sum(o.weight for o in outputs) or 1.0
        weighted_sum = sum(o.weighted_score for o in outputs)
        final_score = round(min(100.0, weighted_sum / total_weight), 2)
        reasons = [o.reason for o in outputs if o.reason]

        return RiskDecision(
            score=final_score,
            disposition=self._decide(final_score),
            reasons=reasons,
            per_scorer=outputs,
        )

    def _decide(self, score: float) -> Disposition:
        if score >= self._block_threshold:
            return deny()
        if score >= self._challenge_threshold:
            return challenge(ChallengeKind.CAPTCHA)
        return allow()
