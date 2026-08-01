"""规则条件操作符的唯一实现。

gateway 的 ConditionEvaluator 与 admin 的规则试跑接口都必须复用这里的实现，
否则「后台预览通过、线上不命中」这类问题极难排查。

新增操作符时同步三处：
  1. 本文件的 OPERATORS 表；
  2. fangyu_shared.schemas.rule._ALLOWED_OPS 白名单；
  3. 前端规则编辑器的操作符下拉选项。
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterable
from typing import Any

_MAX_REGEX_LENGTH = 512


def _is_seq(value: Any) -> bool:
    return isinstance(value, (list, tuple, set, frozenset))


def _as_seq(value: Any) -> Iterable[Any]:
    return value if _is_seq(value) else ()


def op_eq(actual: Any, expected: Any) -> bool:
    return bool(actual == expected)


def op_neq(actual: Any, expected: Any) -> bool:
    return bool(actual != expected)


def _compare(actual: Any, expected: Any) -> int | None:
    """数值比较，无法转换时返回 None 表示不可比。"""
    if isinstance(actual, bool) or isinstance(expected, bool):
        return None
    try:
        left, right = float(actual), float(expected)
    except (TypeError, ValueError):
        return None
    if left == right:
        return 0
    return 1 if left > right else -1


def op_gt(actual: Any, expected: Any) -> bool:
    c = _compare(actual, expected)
    return c is not None and c > 0


def op_gte(actual: Any, expected: Any) -> bool:
    c = _compare(actual, expected)
    return c is not None and c >= 0


def op_lt(actual: Any, expected: Any) -> bool:
    c = _compare(actual, expected)
    return c is not None and c < 0


def op_lte(actual: Any, expected: Any) -> bool:
    c = _compare(actual, expected)
    return c is not None and c <= 0


def op_in(actual: Any, expected: Any) -> bool:
    return any(actual == item for item in _as_seq(expected))


def op_not_in(actual: Any, expected: Any) -> bool:
    if not _is_seq(expected):
        return False
    return not op_in(actual, expected)


def op_in_ci(actual: Any, expected: Any) -> bool:
    """大小写无关集合匹配。用于国家码、设备品牌、爬虫厂商等枚举字段。"""
    if actual is None or not _is_seq(expected):
        return False
    target = str(actual).strip().lower()
    return any(str(item).strip().lower() == target for item in expected if item is not None)


def op_not_in_ci(actual: Any, expected: Any) -> bool:
    if not _is_seq(expected):
        return False
    return not op_in_ci(actual, expected)


def op_contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str):
        return isinstance(expected, str) and expected in actual
    if _is_seq(actual):
        return any(item == expected for item in actual)
    return False


def op_not_contains(actual: Any, expected: Any) -> bool:
    return not op_contains(actual, expected)


def op_startswith(actual: Any, expected: Any) -> bool:
    return isinstance(actual, str) and isinstance(expected, str) and actual.startswith(expected)


def op_endswith(actual: Any, expected: Any) -> bool:
    return isinstance(actual, str) and isinstance(expected, str) and actual.endswith(expected)


def op_regex(actual: Any, expected: Any) -> bool:
    """正则匹配。

    限制模式长度以降低运营误配置写出灾难性回溯正则的风险；
    Python 标准 re 没有超时机制，规则录入侧应做二次审核。
    """
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    if len(expected) > _MAX_REGEX_LENGTH:
        return False
    try:
        return re.search(expected, actual) is not None
    except re.error:
        return False


def _parse_ip(value: Any) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not isinstance(value, str):
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _parse_network(value: Any) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    if not isinstance(value, str):
        return None
    try:
        return ipaddress.ip_network(value.strip(), strict=False)
    except ValueError:
        return None


def op_cidr_in(actual: Any, expected: Any) -> bool:
    """IP 是否落在单个 CIDR 段内。"""
    addr = _parse_ip(actual)
    network = _parse_network(expected)
    if addr is None or network is None:
        return False
    return addr.version == network.version and addr in network


def op_cidr_list_in(actual: Any, expected: Any) -> bool:
    """IP 是否落在任意一个 CIDR 段内。用于 IP 黑白名单批量匹配。

    非法 CIDR 逐条跳过而非整体失败，避免一条脏数据让整个名单失效。
    """
    addr = _parse_ip(actual)
    if addr is None or not _is_seq(expected):
        return False
    for raw in expected:
        network = _parse_network(raw)
        if network is not None and addr.version == network.version and addr in network:
            return True
    return False


def op_cidr_list_not_in(actual: Any, expected: Any) -> bool:
    if not _is_seq(expected):
        return False
    return not op_cidr_list_in(actual, expected)


def coerce_asn(value: Any) -> int | None:
    """归一化 ASN。

    兼容 4134 / "4134" / "AS4134" / "as4134" 四种写法，
    避免运营在后台填 "AS4134" 而 MMDB 返回 int 4134 时静默不命中。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip().upper()
        if text.startswith("AS"):
            text = text[2:].strip()
        if text.isdigit():
            parsed = int(text)
            return parsed if parsed > 0 else None
    return None


def op_asn_in(actual: Any, expected: Any) -> bool:
    """ASN 精准判定。"""
    target = coerce_asn(actual)
    if target is None or not _is_seq(expected):
        return False
    return any(coerce_asn(item) == target for item in expected)


def op_asn_not_in(actual: Any, expected: Any) -> bool:
    if not _is_seq(expected):
        return False
    return not op_asn_in(actual, expected)


OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": op_eq,
    "neq": op_neq,
    "gt": op_gt,
    "gte": op_gte,
    "lt": op_lt,
    "lte": op_lte,
    "in": op_in,
    "not_in": op_not_in,
    "in_ci": op_in_ci,
    "not_in_ci": op_not_in_ci,
    "contains": op_contains,
    "not_contains": op_not_contains,
    "startswith": op_startswith,
    "endswith": op_endswith,
    "regex": op_regex,
    "cidr_in": op_cidr_in,
    "cidr_list_in": op_cidr_list_in,
    "cidr_list_not_in": op_cidr_list_not_in,
    "asn_in": op_asn_in,
    "asn_not_in": op_asn_not_in,
}

OPERATOR_NAMES: frozenset[str] = frozenset(OPERATORS)


def apply_operator(op: str, actual: Any, expected: Any) -> bool:
    """按操作符白名单求值。未知操作符或求值异常统一返回 False。"""
    fn = OPERATORS.get(op)
    if fn is None:
        return False
    try:
        return bool(fn(actual, expected))
    except Exception:
        return False


def read_path(context: dict[str, Any], path: str) -> Any:
    """按点号路径读取嵌套上下文，任一段缺失即返回 None。"""
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
