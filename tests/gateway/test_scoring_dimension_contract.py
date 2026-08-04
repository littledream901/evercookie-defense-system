"""评分维度名与 scorer 名的契约测试。

存在原因
--------
后台评分配置页按 ``SCORING_DIMENSIONS`` 渲染权重表单，网关按
``RiskScorer.name`` 去权重覆盖表里查值（见 ``RiskPipeline.run`` 的
``overrides.get(output.name)``）。两边靠**字符串**对齐，没有任何静态检查：

- 维度 key 拼错或 scorer 改名 → 网关查不到，静默沿用类默认权重。运维的表现是
  「拖了滑块保存成功，但分数一点没变」，且不产生任何错误日志。
- 新增 scorer 忘了加维度 → 该维度在后台完全不可见，权重永远无法调整。

已有 ``test_unknown_scorer_name_in_weights_is_ignored`` 只锁住「陌生 key 不会
连带破坏正常维度」，锁不住「key 与 scorer 名对不上」本身。这里把双向一致性
固化下来。

为什么用文本解析读 admin 侧常量
-------------------------------
``admin-api`` 与 ``gateway-api`` 都以 ``src`` 作为顶层包名，同一个 pytest
进程里只能有一个在 sys.path 上（见根 conftest）。因此不能 import
``admin-api`` 的模块，只能按文本解析出维度 key —— 与
``test_rule_field_contract.py`` 解析前端 ruleFields.ts 同一手法。
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.domain.risk.scorers import (
    BehaviorScorer,
    DeviceScorer,
    IntelScorer,
    InteractionScorer,
    IpReputationScorer,
    ProxyScorer,
    RiskScorer,
    UserAgentScorer,
)

_SCORING_SERVICE = (
    Path(__file__).resolve().parents[2]
    / "admin-api"
    / "src"
    / "application"
    / "services"
    / "scoring_service.py"
)

_GATEWAY_SCORERS: list[type[RiskScorer]] = [
    IpReputationScorer,
    ProxyScorer,
    UserAgentScorer,
    DeviceScorer,
    BehaviorScorer,
    InteractionScorer,
    IntelScorer,
]
"""网关实际装配的 scorer 类，与 ``dependencies.build_decision_service`` 一致。"""


def _parse_dimensions() -> list[dict]:
    """从 admin 侧源码里解析出 SCORING_DIMENSIONS 字面量。

    走 ast 而不是正则：维度表是一串 dict 字面量，``literal_eval`` 能直接拿到
    结构化结果，描述文案里出现括号或引号也不会解析错。
    """
    tree = ast.parse(_SCORING_SERVICE.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "SCORING_DIMENSIONS" in targets:
            return ast.literal_eval(node.value)
    raise AssertionError(
        "未能从 scoring_service.py 解析出 SCORING_DIMENSIONS，常量名或结构已变更"
    )


def test_every_scorer_has_a_dimension():
    """每个 scorer 都必须有对应维度，否则后台无法调它的权重。"""
    dimension_keys = {d["key"] for d in _parse_dimensions()}
    scorer_names = {s.name for s in _GATEWAY_SCORERS}

    missing = scorer_names - dimension_keys
    assert not missing, f"以下 scorer 在后台没有对应维度，权重无法配置: {sorted(missing)}"


def test_every_dimension_maps_to_a_scorer():
    """每个维度都必须对应一个真实 scorer，否则滑块拖了没效果。"""
    dimension_keys = {d["key"] for d in _parse_dimensions()}
    scorer_names = {s.name for s in _GATEWAY_SCORERS}

    orphaned = dimension_keys - scorer_names
    assert not orphaned, f"以下维度在网关侧无对应 scorer，配置会静默失效: {sorted(orphaned)}"


def test_dimensions_carry_chinese_label_and_description():
    """维度必须带中文标签与说明，供前端直接渲染。"""
    for dimension in _parse_dimensions():
        key = dimension["key"]
        assert dimension.get("label"), f"维度 {key} 缺 label"
        assert dimension.get("description"), f"维度 {key} 缺 description"


def test_default_weight_matches_scorer_class_weight():
    """defaultWeight 是 scorer 类默认权重的 10 倍（admin 侧整数量纲）。

    量纲对不上时前端展示的参照值会与网关实际行为不符，运维据此标定必然偏。
    """
    by_name = {s.name: s for s in _GATEWAY_SCORERS}
    for dimension in _parse_dimensions():
        scorer = by_name[dimension["key"]]
        assert dimension["defaultWeight"] == round(scorer.weight * 10), (
            f"维度 {dimension['key']} 的 defaultWeight={dimension['defaultWeight']} "
            f"与 scorer 类权重 {scorer.weight} 换算后不符"
        )
