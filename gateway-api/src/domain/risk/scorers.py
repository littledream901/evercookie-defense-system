"""风险评分器集合。

每个 Scorer 独立、可组合、可插拔，避免 V1 中 1000+ 行 evaluator 巨石。
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import pairwise

from fangyu_shared.clock.behavior import BehaviorKind
from fangyu_shared.schemas.clock import BehaviorEvent

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
    """请求层异常特征：非常规 method、超长 path。

    名字里的 "behavior" 是历史包袱，它看的是**HTTP 请求属性**，与浏览器采集的
    人机行为时序无关。后者由 :class:`InteractionScorer` 负责——两者拆开是因为
    ``applies`` 只能表达一个「有没有输入」：请求属性每条流量都有，行为事件只有
    SDK 路径才有。合成一个 scorer 就必须二选一，要么让 Adapter 流量因为没有
    行为数据而被判可疑，要么让行为信号永远无法报「无数据」。
    """

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


_INTERACTION_KINDS: frozenset[BehaviorKind] = frozenset(
    {
        BehaviorKind.MOUSE_MOVE,
        BehaviorKind.CLICK,
        BehaviorKind.SCROLL,
        BehaviorKind.KEY_PRESS,
    }
)
"""算作「真人在操作」的事件类型。

不含 page_view / focus / blur / submit：
- page_view 是 SDK ``start()`` 无条件补的第一条，与用户操作无关；
- focus / blur 由窗口切换触发，无头浏览器加载页面时同样会产生；
- submit 可以由脚本 ``form.submit()`` 直接触发，不代表有人点过。
"""

_THROTTLED_KINDS: frozenset[BehaviorKind] = frozenset(
    {BehaviorKind.MOUSE_MOVE, BehaviorKind.SCROLL, BehaviorKind.KEY_PRESS}
)
"""SDK 侧按 ``sampleIntervalMs``（默认 200ms）做过同类节流的事件类型。

**判定时序规律性时必须排除这几类。** 采样器给同类事件设了最小间隔，真人连续
移动鼠标时被采下来的点几乎恰好每 200ms 一个——间隔标准差天然接近 0。把这个
采样地板当成「脚本回放的规律性」，等于把所有认真滑动页面的真人判成机器人。
"""

_MIN_TIMING_SAMPLES = 6
"""判定时序规律性所需的最小间隔数（即至少 7 条非节流事件）。

样本太少时低方差没有统计意义：两次点击间隔恰好相同是巧合，不是证据。
"""

_MIN_MEAN_INTERVAL_MS = 250.0
"""平均间隔下限。低于此值的一律不判规律性。

同一个 JS tick 里批量 ``record()`` 出来的事件间隔接近 0，方差也接近 0，但这更
可能是 SDK 自身或页面初始化的批量行为，而不是定时回放。定时回放的特征是
「间隔稳定且不小」。
"""

_MAX_TIMING_CV = 0.05
"""间隔的变异系数（标准差 / 均值）上限。

真人点击、切换窗口的间隔波动很大，CV 普遍在 0.3 以上；``setInterval`` 驱动的
回放脚本 CV 通常低于 0.01。取 0.05 留出定时器抖动的余量，同时离真人的分布
足够远。
"""

_NO_INTERACTION_SPAN_MS = 3000
"""判定「有页面停留但零交互」所需的最小缓冲区时间跨度。

首次 ``decide()`` 紧跟在 SDK ``start()`` 之后触发，缓冲区里通常只有那条
page_view，跨度约为 0——此时用户根本还没有机会操作，不能算信号。要求缓冲区
横跨至少 3 秒，才能说「这段时间里确实没有任何人在操作」。
"""

_MIN_REPEAT_KEYS = 8
"""判定按键 repeat 异常所需的最小 key_press 数。"""

_REPEAT_RATIO_THRESHOLD = 0.9
"""key_press 中 ``repeat=true`` 的占比阈值。

``repeat`` 由浏览器在**长按**时置位，正常输入的绝大多数按键该值为 false。
接近全量 repeat 说明要么是长按（真人删长文本也会这样），要么是伪造载荷统一
填了 true。因此这条只给很低的分，仅作为弱信号参与累加。
"""


class InteractionScorer(RiskScorer):
    """人机交互识别：消费 SDK 采集的行为时序。

    与 :class:`BehaviorScorer` 的分工见后者的文档。

    ``applies=False`` 的语义在这里尤其关键
    --------------------------------------
    没有行为事件时**必须**报「不参与判定」，而不是判成可疑。行为事件只有浏览器
    SDK 路径才会有：Adapter（站点服务端转发）流量在结构上不可能带，站点也可以
    通过 init 下发的 ``collectBehavior=false`` 关停采集。若把「没有行为数据」
    当作风险，所有纯服务端接入会因为「没装浏览器 SDK」而被恒定加分——这不是
    风控结论，而是接入方式的差异。

    各信号都刻意取保守阈值：这里的误判直接表现为真人被拦，代价远高于漏放。
    """

    name = "interaction"
    weight = 0.8

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        events = snapshot.behavior_events
        if not events:
            return self._skip("no_behavior_events")

        score = 0.0
        parts: list[str] = []

        if self._has_page_view_without_interaction(events):
            # 20 分：单独不足以越过挑战线（20 × 0.8 = 16），需与其他维度累加。
            # 真人读完一屏不滚动就离开也会命中，不能让它单独定罪。
            score += 20
            parts.append("no_interaction")

        cv = self._interval_cv(events)
        if cv is not None and cv < _MAX_TIMING_CV:
            # 30 分：定时回放是本 scorer 里最硬的信号，但仍压在挑战线之下
            # （30 × 0.8 = 24），留给 IP / 设备 / UA 维度共同定性。
            score += 30
            parts.append(f"regular_timing:cv={cv:.4f}")

        if self._is_repeat_key_burst(events):
            score += 12
            parts.append("key_repeat_burst")

        reason = "+".join(parts) if parts else None
        # 注意：无信号时返回 score=0 且 applies=True —— 「已评估，无风险」，
        # 与上面的 _skip（拿不到输入）是不同结论，排障时必须能区分。
        return ScorerOutput(
            name=self.name, score=min(score, 100.0), reason=reason, weight=self.weight
        )

    @staticmethod
    def _has_page_view_without_interaction(events: tuple[BehaviorEvent, ...]) -> bool:
        """有 page_view、跨度够长，却没有任何交互类事件。

        无头/脚本流量的典型形状：page_view + focus/blur 齐全（这些由页面加载
        本身触发），但鼠标、滚动、键盘全空。
        """
        if not any(e.kind == BehaviorKind.PAGE_VIEW for e in events):
            return False
        if any(e.kind in _INTERACTION_KINDS for e in events):
            return False
        timestamps = [e.client_ts_ms for e in events]
        span = max(timestamps) - min(timestamps)
        return span >= _NO_INTERACTION_SPAN_MS

    @staticmethod
    def _interval_cv(events: tuple[BehaviorEvent, ...]) -> float | None:
        """非节流事件的相邻间隔变异系数。``None`` 表示样本不足以判定。

        只取非节流类型，避免把 SDK 的 200ms 采样地板误读成脚本的规律性
        （见 :data:`_THROTTLED_KINDS`）。
        """
        timestamps = sorted(
            e.client_ts_ms for e in events if e.kind not in _THROTTLED_KINDS
        )
        if len(timestamps) < _MIN_TIMING_SAMPLES + 1:
            return None

        intervals = [float(b - a) for a, b in pairwise(timestamps)]
        mean = sum(intervals) / len(intervals)
        if mean < _MIN_MEAN_INTERVAL_MS:
            return None
        variance = sum((i - mean) ** 2 for i in intervals) / len(intervals)
        return math.sqrt(variance) / mean

    @staticmethod
    def _is_repeat_key_burst(events: tuple[BehaviorEvent, ...]) -> bool:
        """key_press 数量够多且几乎全部带 ``repeat`` 标记。"""
        presses = [e for e in events if e.kind == BehaviorKind.KEY_PRESS]
        if len(presses) < _MIN_REPEAT_KEYS:
            return False
        repeats = sum(1 for e in presses if e.data.get("repeat") is True)
        return repeats / len(presses) >= _REPEAT_RATIO_THRESHOLD


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
