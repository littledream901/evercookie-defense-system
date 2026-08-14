"""风险评分器集合。

每个 Scorer 独立、可组合、可插拔，避免 V1 中 1000+ 行 evaluator 巨石。

评分常量的来源
----------------
所有影响「评分结果」的数值常量统一收敛到 :data:`DEFAULT_SCORER_PARAMS`，不再
散落在各 Scorer 内部。站点级配置 ``scorer_params``（经评分配置页下发）可以按
``scorer 名 → 参数键`` 覆盖其中任意一项；未覆盖的键回退到这里的默认值。

以下内容**不是**评分配置，保持为模块级结构常量：
- ``_SUSPICIOUS_UA_RE``：UA 兜底判定的正则模式（算法结构，非数值旋钮）；
- ``_INTERACTION_KINDS`` / ``_THROTTLED_KINDS``：行为事件类型集合（协议契约）；
- ``IpReputationScorer`` / ``IntelScorer``：直接由外部信誉分 / 情报分推导，
  无内部评分常量。
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from fangyu_shared.clock.behavior import BehaviorKind
from fangyu_shared.schemas.clock import BehaviorEvent

from src.domain.profile.builder import ProfileSnapshot


@dataclass(frozen=True, slots=True)
class ScorerOutput:
    """单个 scorer 的产出。

    **只负责「评分」，不负责「权重」**。权重是业务策略，由评分配置系统统一
    下发，在 ``RiskPipeline.run(weights=...)`` 里按 scorer 名应用，因此这里
    不携带 ``weight`` 字段——避免「类默认权重」与「配置权重」两套来源互相打架。

    ``applies``
        本次是否参与判定。**「不参与」与「判定为 0 分」是两件事**：前者表示
        该 scorer 拿不到输入（如 IP 信誉库无此 IP），后者表示已评估且无风险。
        混为一谈会让排障时无法区分「没查到」和「查到了是干净的」，也会让
        缺数据源的 scorer 悄悄贡献一个虚假基线分。
    """

    name: str
    score: float
    reason: str | None = None
    applies: bool = True


class RiskScorer(ABC):
    name: str = "base"

    @abstractmethod
    def score(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None = None
    ) -> ScorerOutput: ...

    def _skip(self, reason: str | None = None) -> ScorerOutput:
        """产出「未参与」结果。分数为 0 且不计入累加。"""
        return ScorerOutput(
            name=self.name, score=0.0, reason=reason, applies=False
        )

    def _merged(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """把站点级参数覆盖合并到本 scorer 的默认参数上（浅合并）。

        嵌套映射表（如 ``connection_types``）作为整体键覆盖：前端传了就用前端
        的，没传就用默认表，不做逐键深合并——避免「传一半丢一半」的歧义。
        """
        defaults = DEFAULT_SCORER_PARAMS.get(self.name, {})
        merged: dict[str, Any] = dict(defaults)
        if params:
            merged.update(params)
        return merged

    @staticmethod
    def _num(params: dict[str, Any], key: str, default: float) -> float:
        """读取标量参数，类型非法时回退默认值，防止 JSON 里混入脏数据。"""
        value = params.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return float(value)


# ---------------------------------------------------------------------------
# 默认评分参数：所有影响评分结果的数值常量集中于此，前端可覆盖。
# ---------------------------------------------------------------------------
DEFAULT_SCORER_PARAMS: dict[str, dict[str, Any]] = {
    "proxy": {
        "tor": 55.0,
        "vpn": 30.0,
        "proxy": 25.0,
        "datacenter": 30.0,
        "mobile_discount": 0.4,
        # 按 MMDBReader 推断出的网络类型给分。
        # unknown 给 10 分而非 0：ASN 库查不到的 IP 多为新分配段或私有地址，
        # 比已确认的住宅网络更可疑，但不足以单独构成拦截理由。
        "connection_types": {
            "datacenter": 35.0,
            "education": 5.0,
            "government": 0.0,
            "mobile": 0.0,
            "residential": 0.0,
            "unknown": 10.0,
        },
    },
    "user_agent": {
        "empty_ua": 40.0,
        "suspicious_ua": 70.0,
        "unparsable_ua": 30.0,
        "unknown_client": 15.0,
        "unknown_device": 10.0,
        "crawler_default": 35.0,
        # 按爬虫类别给分。
        # search_engine 给 0 分是有意的：搜索引擎抓取影响 SEO 收录，
        # 拦截代价由业务承担，应交给显式规则（白名单）而不是风险分累积。
        "crawler_categories": {
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
        },
    },
    "device": {
        "new_device": 25.0,
        "high_block_rate_threshold": 0.5,
    },
    "behavior": {
        "method_anomaly": 30.0,
        "long_path": 20.0,
        "max_path_length": 512.0,
    },
    "interaction": {
        "no_interaction": 20.0,
        "regular_timing": 30.0,
        "key_repeat_burst": 12.0,
        # 时序规律性判定阈值
        "min_timing_samples": 6.0,
        "min_mean_interval_ms": 250.0,
        "max_timing_cv": 0.05,
        # 零交互停留判定阈值
        "no_interaction_span_ms": 3000.0,
        # 按键 repeat 异常判定阈值
        "min_repeat_keys": 8.0,
        "repeat_ratio_threshold": 0.9,
    },
}


class IpReputationScorer(RiskScorer):
    """IP 历史信誉。数据来自 worker 的信誉回写任务。

    无信誉数据时**不参与判定**，而不是拿默认 50 分当中等风险。信誉库为空的
    环境下（新部署、回写任务未跑）每个 IP 都白拿一份基线分，会把整体分数
    抬高一个固定量，等于变相下调了阈值。
    """

    name = "ip_reputation"

    def score(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None = None
    ) -> ScorerOutput:
        ip = snapshot.ip
        if not ip.has_reputation:
            return self._skip("no_reputation_data")
        reputation = ip.reputation_score
        score = max(0.0, 100.0 - reputation)
        reason = f"ip_reputation={reputation:.1f}" if score > 30 else None
        return ScorerOutput(name=self.name, score=score, reason=reason)


class ProxyScorer(RiskScorer):
    """网络层风险：代理 / VPN / Tor / 数据中心 / 移动网络。

    移动网络单独降权：蜂窝出口 IP 由大量真实用户共享（CGNAT），
    误杀代价远高于放过，因此即使命中其他弱信号也压低总分。
    """

    name = "proxy"

    def score(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None = None
    ) -> ScorerOutput:
        p = self._merged(params)
        ip = snapshot.ip
        score = 0.0
        parts: list[str] = []

        if ip.is_tor:
            score += self._num(p, "tor", 55.0)
            parts.append("tor")
        if ip.is_vpn:
            score += self._num(p, "vpn", 30.0)
            parts.append("vpn")
        elif ip.is_proxy:
            score += self._num(p, "proxy", 25.0)
            parts.append("proxy")

        connection_types = p.get("connection_types") or {}
        conn_score = float(connection_types.get(ip.connection_type, 0.0))
        if conn_score > 0:
            score += conn_score
            parts.append(ip.connection_type)
        elif ip.is_datacenter:
            score += self._num(p, "datacenter", 30.0)
            parts.append("datacenter")

        if ip.is_mobile_network and not (ip.is_tor or ip.is_vpn):
            score *= self._num(p, "mobile_discount", 0.4)
            parts.append("mobile_discount")

        reason = "+".join(part for part in parts if part) or None
        return ScorerOutput(name=self.name, score=min(score, 100.0), reason=reason)


_SUSPICIOUS_UA_RE = re.compile(
    r"(curl|wget|python-requests|scrapy|httpclient|okhttp|headless|phantomjs|nikto|sqlmap)",
    re.IGNORECASE,
)


class UserAgentScorer(RiskScorer):
    """UA 层风险：基于结构化解析结果而非单条正则。"""

    name = "user_agent"

    def score(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None = None
    ) -> ScorerOutput:
        ua = snapshot.ua
        if ua is None:
            return self._fallback(snapshot, params)

        p = self._merged(params)

        if ua.is_empty:
            return ScorerOutput(
                name=self.name,
                score=self._num(p, "empty_ua", 40.0),
                reason="empty_ua",
            )

        if ua.crawler_category:
            crawler_categories = p.get("crawler_categories") or {}
            score = float(
                crawler_categories.get(
                    ua.crawler_category, self._num(p, "crawler_default", 35.0)
                )
            )
            reason = f"{ua.crawler_category}:{ua.crawler_vendor or 'unknown'}"
            return ScorerOutput(name=self.name, score=score, reason=reason)

        parts: list[str] = []
        score = 0.0
        if ua.os == "unknown" and ua.browser == "unknown":
            score += self._num(p, "unparsable_ua", 30.0)
            parts.append("unparsable_ua")
        elif ua.browser == "unknown":
            score += self._num(p, "unknown_client", 15.0)
            parts.append("unknown_client")
        if ua.device_type == "unknown":
            score += self._num(p, "unknown_device", 10.0)
            parts.append("unknown_device")

        reason = "+".join(parts) if parts else None
        return ScorerOutput(name=self.name, score=min(score, 100.0), reason=reason)

    def _fallback(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None
    ) -> ScorerOutput:
        """ua 缺失时退回原正则判定，保证旧调用路径不失效。"""
        p = self._merged(params)
        raw = snapshot.context.get("request", {}).get("user_agent", "")
        if not raw:
            return ScorerOutput(
                name=self.name, score=self._num(p, "empty_ua", 40.0), reason="empty_ua"
            )
        if _SUSPICIOUS_UA_RE.search(raw):
            return ScorerOutput(
                name=self.name, score=self._num(p, "suspicious_ua", 70.0), reason="suspicious_ua"
            )
        return ScorerOutput(name=self.name, score=0.0)


class DeviceScorer(RiskScorer):
    """设备历史行为。

    新设备给 25 分是**参与判定**的结论而非缺数据：首次出现本身就是弱风险信号。
    但设备已有访问记录、仅缺信誉分时不再退回默认 50 分基线，
    与 :class:`IpReputationScorer` 同理。
    """

    name = "device"

    def score(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None = None
    ) -> ScorerOutput:
        p = self._merged(params)
        device = snapshot.device
        if device.total_requests == 0:
            return ScorerOutput(
                name=self.name, score=self._num(p, "new_device", 25.0), reason="new_device"
            )
        if device.blocked_requests > 0:
            block_rate = device.blocked_requests / device.total_requests
            if block_rate > self._num(p, "high_block_rate_threshold", 0.5):
                return ScorerOutput(
                    name=self.name,
                    score=min(100.0, block_rate * 100),
                    reason=f"high_block_rate={block_rate:.2f}",
                )
        if not device.has_reputation:
            return self._skip("no_reputation_data")
        return ScorerOutput(
            name=self.name,
            score=max(0.0, 100.0 - device.reputation_score),
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

    def score(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None = None
    ) -> ScorerOutput:
        p = self._merged(params)
        request = snapshot.context.get("request", {})
        method = str(request.get("method", "GET")).upper()
        path = str(request.get("path", "/"))
        score = 0.0
        parts: list[str] = []
        if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}:
            score += self._num(p, "method_anomaly", 30.0)
            parts.append(f"method_anomaly:{method}")
        if len(path) > int(self._num(p, "max_path_length", 512.0)):
            score += self._num(p, "long_path", 20.0)
            parts.append("long_path")
        reason = "+".join(parts) if parts else None
        return ScorerOutput(name=self.name, score=score, reason=reason)


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

    def score(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None = None
    ) -> ScorerOutput:
        events = snapshot.behavior_events
        if not events:
            return self._skip("no_behavior_events")

        p = self._merged(params)
        score = 0.0
        parts: list[str] = []

        no_interaction_span_ms = self._num(p, "no_interaction_span_ms", 3000.0)
        min_timing_samples = int(self._num(p, "min_timing_samples", 6.0))
        min_mean_interval_ms = self._num(p, "min_mean_interval_ms", 250.0)
        max_timing_cv = self._num(p, "max_timing_cv", 0.05)
        min_repeat_keys = int(self._num(p, "min_repeat_keys", 8.0))
        repeat_ratio_threshold = self._num(p, "repeat_ratio_threshold", 0.9)

        if self._has_page_view_without_interaction(events, no_interaction_span_ms):
            # 单独不足以越过挑战线，需与其他维度累加。
            # 真人读完一屏不滚动就离开也会命中，不能让它单独定罪。
            score += self._num(p, "no_interaction", 20.0)
            parts.append("no_interaction")

        cv = self._interval_cv(events, min_timing_samples, min_mean_interval_ms)
        if cv is not None and cv < max_timing_cv:
            # 定时回放是本 scorer 里最硬的信号，但仍压在挑战线之下，
            # 留给 IP / 设备 / UA 维度共同定性。
            score += self._num(p, "regular_timing", 30.0)
            parts.append(f"regular_timing:cv={cv:.4f}")

        if self._is_repeat_key_burst(events, min_repeat_keys, repeat_ratio_threshold):
            score += self._num(p, "key_repeat_burst", 12.0)
            parts.append("key_repeat_burst")

        reason = "+".join(parts) if parts else None
        # 注意：无信号时返回 score=0 且 applies=True —— 「已评估，无风险」，
        # 与上面的 _skip（拿不到输入）是不同结论，排障时必须能区分。
        return ScorerOutput(
            name=self.name, score=min(score, 100.0), reason=reason
        )

    @staticmethod
    def _has_page_view_without_interaction(
        events: tuple[BehaviorEvent, ...], no_interaction_span_ms: float
    ) -> bool:
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
        return span >= no_interaction_span_ms

    @staticmethod
    def _interval_cv(
        events: tuple[BehaviorEvent, ...],
        min_timing_samples: int,
        min_mean_interval_ms: float,
    ) -> float | None:
        """非节流事件的相邻间隔变异系数。``None`` 表示样本不足以判定。

        只取非节流类型，避免把 SDK 的 200ms 采样地板误读成脚本的规律性
        （见 :data:`_THROTTLED_KINDS`）。
        """
        timestamps = sorted(
            e.client_ts_ms for e in events if e.kind not in _THROTTLED_KINDS
        )
        if len(timestamps) < min_timing_samples + 1:
            return None

        intervals = [float(b - a) for a, b in pairwise(timestamps)]
        mean = sum(intervals) / len(intervals)
        if mean < min_mean_interval_ms:
            return None
        variance = sum((i - mean) ** 2 for i in intervals) / len(intervals)
        return math.sqrt(variance) / mean

    @staticmethod
    def _is_repeat_key_burst(
        events: tuple[BehaviorEvent, ...],
        min_repeat_keys: int,
        repeat_ratio_threshold: float,
    ) -> bool:
        """key_press 数量够多且几乎全部带 ``repeat`` 标记。"""
        presses = [e for e in events if e.kind == BehaviorKind.KEY_PRESS]
        if len(presses) < min_repeat_keys:
            return False
        repeats = sum(1 for e in presses if e.data.get("repeat") is True)
        return repeats / len(presses) >= repeat_ratio_threshold


class IntelScorer(RiskScorer):
    """消费后台维护的六类维度情报评分。

    情报是人工录入的确定性结论，risk_score 已是 0-100 量纲，不需要再放大或
    衰减。正规爬虫（is_legitimate）不计分，避免搜索引擎被拦。
    """

    name = "intel"

    def score(
        self, snapshot: ProfileSnapshot, params: dict[str, Any] | None = None
    ) -> ScorerOutput:
        intel = snapshot.intel
        if intel is None or not intel.matched:
            return self._skip("no_intel_match")
        if intel.is_legitimate_crawler and intel.risk_score == 0:
            return ScorerOutput(
                name=self.name, score=0.0, reason="legitimate_crawler"
            )
        return ScorerOutput(
            name=self.name,
            score=float(intel.risk_score),
            reason="+".join(intel.reasons),
        )
