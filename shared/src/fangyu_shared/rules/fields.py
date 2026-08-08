"""规则条件可用字段注册表。

存在原因
--------
条件的 ``field`` 是字符串，:class:`RuleBase` 只校验顶层命名空间（device/ip/
ua/request/intel），不校验叶子名。因此 ``device.isNew``、``ip.category`` 这类
上下文里根本不存在的字段能通过校验、正常落库、正常发布，却**永远不会命中**，
且不产生任何错误日志。

本模块把「规则能引用哪些字段」显式声明出来，作为三方共同基准：
  - gateway 侧有契约测试断言本表与真实评估上下文完全一致；
  - admin 侧规则模板与规则写入校验引用本表；
  - 前端字段下拉表由契约测试与本表比对。

新增画像字段时，改 :mod:`fangyu_shared.schemas.profile` 之后必须同步本表，
否则 gateway 侧契约测试失败。
"""

from __future__ import annotations

CONTEXT_FIELDS: frozenset[str] = frozenset(
    {
        # ── device.*：设备画像。注意是 camelCase，走 model_dump(by_alias=True) ──
        "device.fingerprint",
        "device.deviceId",
        "device.firstSeenAt",
        "device.lastSeenAt",
        "device.totalRequests",
        "device.blockedRequests",
        "device.reputationScore",
        "device.reputationSamples",
        "device.tags",
        "device.extra",
        # ── ip.*：IP 画像，同为 camelCase ──
        "ip.ip",
        "ip.ipType",
        "ip.continent",
        "ip.country",
        "ip.region",
        "ip.city",
        "ip.asn",
        "ip.asnOrg",
        "ip.isp",
        "ip.connectionType",
        "ip.isProxy",
        "ip.isVpn",
        "ip.isTor",
        "ip.isDatacenter",
        "ip.isMobileNetwork",
        "ip.reputationScore",
        "ip.reputationSamples",
        "ip.totalRequests",
        "ip.lastSeenAt",
        # ── ua.*：UA 解析结果，snake_case（来自 dataclass asdict）──
        "ua.device_type",
        "ua.os",
        "ua.os_version",
        "ua.browser",
        "ua.browser_version",
        "ua.engine",
        "ua.brand",
        "ua.model",
        "ua.client_type",
        "ua.client_name",
        "ua.is_bot",
        "ua.is_mobile",
        "ua.crawler_name",
        "ua.crawler_category",
        "ua.crawler_vendor",
        "ua.crawler_verifiable",
        "ua.is_empty",
        # ── request.*：本次请求属性，snake_case ──
        "request.path",
        "request.method",
        "request.user_agent",
        "request.referer",
        "request.session_id",
        "request.has_referer",
        # ── intel.*：后台情报命中结果，snake_case ──
        "intel.matched",
        "intel.risk_score",
        "intel.reasons",
        "intel.crawler_category",
        "intel.crawler_name",
        "intel.is_legitimate_crawler",
    }
)
"""规则条件可引用的全部字段路径。

命名风格按命名空间不同：``device.*`` / ``ip.*`` 是 camelCase（Pydantic
by_alias），``ua.*`` / ``request.*`` / ``intel.*`` 是 snake_case。写
``ip.is_proxy`` 不会报错，但永远取不到值。
"""

NULLABLE_FIELDS: frozenset[str] = frozenset(
    {
        "device.deviceId",
        "ip.continent",
        "ip.country",
        "ip.region",
        "ip.city",
        "ip.asn",
        "ip.asnOrg",
        "ip.isp",
        "ua.os_version",
        "ua.browser_version",
        "ua.model",
        "ua.crawler_name",
        "ua.crawler_category",
        "ua.crawler_vendor",
        "request.referer",
        "request.session_id",
        "intel.crawler_category",
        "intel.crawler_name",
    }
)
"""运行时可能为 ``None`` 的字段。

这些字段配否定类操作符（``not_in`` / ``not_in_ci`` / ``neq`` / ``asn_not_in``
/ ``cidr_list_not_in``）时，**取值为空即命中**。「非白名单国家一律拦截」需要
该行为才能表达，代价是 MMDB 未加载时会拦下全部流量，因此这类规则必须额外
加一条「字段不等于空」的前置条件。
"""

NEGATIVE_OPERATORS: frozenset[str] = frozenset(
    {"neq", "not_in", "not_in_ci", "asn_not_in", "cidr_list_not_in"}
)
"""取值为 ``None`` 时会命中的操作符。

``not_contains`` 不在其中：它对 ``None`` 与非字符串返回 False，因为它常被
用在数值/布尔字段上，若也 fail-open 会让条件恒成立。
"""


def is_valid_field(field: str) -> bool:
    """字段是否可在运行时取到值。"""
    return field in CONTEXT_FIELDS


def has_null_risk(field: str, op: str) -> bool:
    """该字段与操作符的组合是否存在「数据缺失即命中」的误杀风险。"""
    return field in NULLABLE_FIELDS and op in NEGATIVE_OPERATORS
