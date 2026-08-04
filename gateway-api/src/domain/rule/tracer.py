"""规则条件命中明细的采集与采样。

为什么明细是「事后重算」而不是匹配时收集
----------------------------------------
``DecisionRuleMatcher`` 的 ``_hits`` 只返回 bool，逐条件的实际值在
``evaluate_conditions`` 内部就被丢掉了。要在匹配过程中留下明细，只有两条路：

1. 让匹配器对**每个请求的每条规则的每个条件**都构造一条 trace 记录。
   规则数 × 条件数的字典分配全落在决策热路径上，而 99% 的流量最终既不写明细
   也不会有人查——为 1% 的排障需求给 100% 的请求加开销。
2. 决策完成后，用同一个 eval context 对**需要留痕的那几条规则**重算一遍。

这里选 2。重算是安全的：``read_path`` 与 ``apply_operator`` 都是纯函数，
输入（context + condition）完全相同，结果必然与决策时一致——不存在「明细显示
命中但决策没命中」这种自相矛盾的可能。代价是多跑一次算子，但只发生在已经
决定要留痕的请求上，且规则数量是运营配置量级。

采样策略（对齐 init.sql 中 decision_traces 的表注释）
----------------------------------------------------
- 非 trusted 裁决：全量留痕。这些正是需要回答「为什么被拦」的请求。
- trusted 裁决：按 ``sample_rate`` 抽样。正常流量占绝对多数，全量留痕会让
  这张表的写入量与主表持平，而它的价值只在于「对照组」。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from fangyu_shared.rules.operators import apply_operator, read_path
from fangyu_shared.schemas.rule import DecisionRule

# 单个请求最多留痕的条件数。规则配错（比如一条规则塞了几百个条件）时，
# 这个上限保证单请求的写入量有界。
_MAX_TRACES_PER_REQUEST = 200

# expected / actual 落库前的截断长度，与 ClickHouse 侧 String 列的用途一致：
# 只用于排障展示，不参与判定。CIDR 名单这类 value 可能极长。
_MAX_VALUE_LENGTH = 512


@dataclass(frozen=True, slots=True)
class ConditionTrace:
    """单个条件的求值明细。"""

    rule_id: int
    rule_name: str
    field_path: str
    op: str
    expected: str
    actual: str
    matched: bool


def should_trace(*, verdict_is_trusted: bool, sample_rate: float) -> bool:
    """按采样策略决定这次请求是否留痕。

    ``sample_rate <= 0`` 时 trusted 流量完全不留痕；``>= 1`` 时全量留痕。
    非 trusted 一律返回 True，不受采样率影响——排障时「这条被拦的请求查不到
    明细」是最没法接受的情况。
    """
    if not verdict_is_trusted:
        return True
    if sample_rate <= 0:
        return False
    if sample_rate >= 1:
        return True
    return random.random() < sample_rate


def collect_condition_traces(
    rules: list[DecisionRule],
    context: dict[str, Any],
    *,
    limit: int = _MAX_TRACES_PER_REQUEST,
) -> list[ConditionTrace]:
    """对给定规则逐条件重算，产出明细。

    ``rules`` 由调用方筛选——通常是「参与过本次决策的规则」，而不是全部规则。
    对没参与决策的规则留痕没有意义，只会放大写入量。
    """
    traces: list[ConditionTrace] = []
    for rule in rules:
        if rule.id is None:
            # 未落库的规则（试跑构造的临时对象）没有稳定 id，
            # 写进按 (app_id, request_id, rule_id) 排序的表里无法定位。
            continue
        for condition in rule.conditions:
            if len(traces) >= limit:
                return traces
            actual = read_path(context, condition.field)
            traces.append(
                ConditionTrace(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    field_path=condition.field,
                    op=condition.op,
                    expected=_stringify(condition.value),
                    actual=_stringify(actual),
                    matched=apply_operator(condition.op, actual, condition.value),
                )
            )
    return traces


def _stringify(value: Any) -> str:
    """把任意条件值压成可落库的短字符串。

    列表只取前若干项：CIDR / ASN 名单动辄上千条，完整落库对排障没有额外信息
    （真正要看的是「实际值是什么」），却会把冷表撑大一个数量级。
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        head = ",".join(str(v) for v in items[:8])
        suffix = f",...(+{len(items) - 8})" if len(items) > 8 else ""
        return f"[{head}{suffix}]"[:_MAX_VALUE_LENGTH]
    return str(value)[:_MAX_VALUE_LENGTH]
