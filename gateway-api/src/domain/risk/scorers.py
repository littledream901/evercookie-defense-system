"""风险评分器集合。

每个 Scorer 独立、可组合、可插拔，避免 V1 中 1000+ 行 evaluator 巨石。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.profile.builder import ProfileSnapshot


@dataclass(frozen=True, slots=True)
class ScorerOutput:
    """单个 scorer 的产出。

    ``applies``
        本次是否参与判定。**「不参与」与「判定为 0 分」是两件事**：前者表示
        该 scorer 拿不到输入（如 IP 信誉库无此 IP），后者表示已评估且无风险。
        混为一谈会让排障时无法区分「没查到」和「查到了是干净的」，也会让
        缺数据源的 scorer 悄悄贡献一个虚假基线分。
    """

    name: str
    score: float
    reason: str | None = None
    weight: float = 1.0
    applies: bool = True

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight

    def with_weight(self, weight: float) -> ScorerOutput:
        """返回替换权重后的副本，供库中 ScoringRule 覆盖类默认权重。"""
        return ScorerOutput(
            name=self.name,
            score=self.score,
            reason=self.reason,
            weight=weight,
            applies=self.applies,
        )


class RiskScorer(ABC):
    name: str = "base"
    weight: float = 1.0

    @abstractmethod
    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput: ...

    def _skip(self, reason: str | None = None) -> ScorerOutput:
        """产出「未参与」结果。分数为 0 且不计入累加。"""
        return ScorerOutput(
            name=self.name, score=0.0, reason=reason, weight=self.weight, applies=False
        )


class IpReputationScorer(RiskScorer):
    """IP 历史信誉。数据来自 worker 的信誉回写任务。

    无信誉数据时**不参与判定**，而不是拿默认 50 分当中等风险。信誉库为空的
    环境下（新部署、回写任务未跑）每个 IP 都白拿一份基线分，会把整体分数
    抬高一个固定量，等于变相下调了阈值。
    """

    name = "ip_reputation"
    weight = 1.2

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        ip = snapshot.ip
        if not ip.has_reputation:
            return self._skip("no_reputation_data")
        reputation = ip.reputation_score
        score = max(0.0, 100.0 - reputation)
        reason = f"ip_reputation={reputation:.1f}" if score > 30 else None
        return ScorerOutput(name=self.name, score=score, reason=reason, weight=self.weight)


_CONNECTION_TYPE_SCORES: dict[str, float] = {
    "datacenter": 35.0,
    "education": 5.0,
    "government": 0.0,
    "mobile": 0.0,
    "residential": 0.0,
    "unknown": 10.0,
}
"""按 MMDBReader 推断出的网络类型给分。

unknown 给 10 分而非 0：ASN 库查不到的 IP 多为新分配段或私有地址，
比已确认的住宅网络更可疑，但不足以单独构成拦截理由。
"""


class ProxyScorer(RiskScorer):
    """网络层风险：代理 / VPN / Tor / 数据中心 / 移动网络。

    移动网络单独降权：蜂窝出口 IP 由大量真实用户共享（CGNAT），
    误杀代价远高于放过，因此即使命中其他弱信号也压低总分。
    """

    name = "proxy"
    weight = 1.5

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        ip = snapshot.ip
        score = 0.0
        parts: list[str] = []

        if ip.is_tor:
            score += 55
            parts.append("tor")
        if ip.is_vpn:
            score += 30
            parts.append("vpn")
        elif ip.is_proxy:
            score += 25
            parts.append("proxy")

        conn_score = _CONNECTION_TYPE_SCORES.get(ip.connection_type, 0.0)
        if conn_score > 0:
            score += conn_score
            parts.append(ip.connection_type)
        elif ip.is_datacenter:
            score += 30
            parts.append("datacenter")

        if ip.is_mobile_network and not (ip.is_tor or ip.is_vpn):
            score *= 0.4
            parts.append("mobile_discount")

        reason = "+".join(p for p in parts if p) or None
        return ScorerOutput(name=self.name, score=min(score, 100.0), reason=reason, weight=self.weight)


_CRAWLER_CATEGORY_SCORES: dict[str, float] = {
    "security": 95.0,
    "library": 70.0,
    "ai_crawler": 45.0,
    "seo": 40.0,
    "archive": 30.0,
    "other": 35.0,
    "feed": 10.0,
    "monitoring": 10.0,
    "social": 5.0,
    "search_engine": 0.0,
}
"""按爬虫类别给分。

search_engine 给 0 分是有意的：搜索引擎抓取影响 SEO 收录，
拦截代价由业务承担，应交给显式规则（白名单）而不是风险分累积。
"""

_SUSPICIOUS_UA_RE = re.compile(
    r"(curl|wget|python-requests|scrapy|httpclient|okhttp|headless|phantomjs|nikto|sqlmap)",
    re.IGNORECASE,
)


class UserAgentScorer(RiskScorer):
    """UA 层风险：基于结构化解析结果而非单条正则。"""

    name = "user_agent"
    weight = 0.8

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        ua = snapshot.ua
        if ua is None:
            return self._fallback(snapshot)

        if ua.is_empty:
            return ScorerOutput(name=self.name, score=40.0, reason="empty_ua", weight=self.weight)

        if ua.crawler_category:
            score = _CRAWLER_CATEGORY_SCORES.get(ua.crawler_category, 35.0)
            reason = f"{ua.crawler_category}:{ua.crawler_vendor or 'unknown'}"
            return ScorerOutput(name=self.name, score=score, reason=reason, weight=self.weight)

        parts: list[str] = []
        score = 0.0
        if ua.os == "unknown" and ua.browser == "unknown":
            score += 30
            parts.append("unparsable_ua")
        elif ua.browser == "unknown":
            score += 15
            parts.append("unknown_client")
        if ua.device_type == "unknown":
            score += 10
            parts.append("unknown_device")

        reason = "+".join(parts) if parts else None
        return ScorerOutput(name=self.name, score=min(score, 100.0), reason=reason, weight=self.weight)

    def _fallback(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        """ua 缺失时退回原正则判定，保证旧调用路径不失效。"""
        raw = snapshot.context.get("request", {}).get("user_agent", "")
        if not raw:
            return ScorerOutput(name=self.name, score=40.0, reason="empty_ua", weight=self.weight)
        if _SUSPICIOUS_UA_RE.search(raw):
            return ScorerOutput(name=self.name, score=70.0, reason="suspicious_ua", weight=self.weight)
        return ScorerOutput(name=self.name, score=0.0, weight=self.weight)


class DeviceScorer(RiskScorer):
    """设备历史行为。

    新设备给 25 分是**参与判定**的结论而非缺数据：首次出现本身就是弱风险信号。
    但设备已有访问记录、仅缺信誉分时不再退回默认 50 分基线，
    与 :class:`IpReputationScorer` 同理。
    """

    name = "device"
    weight = 1.0

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        device = snapshot.device
        if device.total_requests == 0:
            return ScorerOutput(name=self.name, score=25.0, reason="new_device", weight=self.weight)
        if device.blocked_requests > 0:
            block_rate = device.blocked_requests / device.total_requests
            if block_rate > 0.5:
                return ScorerOutput(
                    name=self.name,
                    score=min(100.0, block_rate * 100),
                    reason=f"high_block_rate={block_rate:.2f}",
                    weight=self.weight,
                )
        if not device.has_reputation:
            return self._skip("no_reputation_data")
        return ScorerOutput(
            name=self.name,
            score=max(0.0, 100.0 - device.reputation_score),
            weight=self.weight,
        )


class BehaviorScorer(RiskScorer):
    name = "behavior"
    weight = 1.0

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        request = snapshot.context.get("request", {})
        method = str(request.get("method", "GET")).upper()
        path = str(request.get("path", "/"))
        score = 0.0
        parts = []
        if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}:
            score += 30
            parts.append(f"method_anomaly:{method}")
        if len(path) > 512:
            score += 20
            parts.append("long_path")
        reason = "+".join(parts) if parts else None
        return ScorerOutput(name=self.name, score=score, reason=reason, weight=self.weight)


class IntelScorer(RiskScorer):
    """消费后台维护的六类维度情报评分。

    权重设为 1.0：情报是人工录入的确定性结论，risk_score 已是 0-100 量纲，
    不需要再放大或衰减。正规爬虫（is_legitimate）不计分，避免搜索引擎被拦。
    """

    name = "intel"
    weight = 1.0

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        intel = snapshot.intel
        if intel is None or not intel.matched:
            return self._skip("no_intel_match")
        if intel.is_legitimate_crawler and intel.risk_score == 0:
            return ScorerOutput(
                name=self.name, score=0.0, reason="legitimate_crawler", weight=self.weight
            )
        return ScorerOutput(
            name=self.name,
            score=float(intel.risk_score),
            reason="+".join(intel.reasons),
            weight=self.weight,
        )
