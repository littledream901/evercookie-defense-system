"""规则条件字段契约测试。

存在原因
--------
规则条件的 ``field`` 是字符串，schema 只校验顶层命名空间（device/ip/ua/
request/intel），不校验叶子名。因此 ``device.isNew``、``ip.category`` 这类
上下文里根本不存在的字段能通过校验、正常落库、正常发布，只是**永远不会命中**，
且不产生任何错误日志——只有对着真实流量做命中率统计才能发现。

本测试把「条件字段必须存在于真实评估上下文」这条契约固化下来，覆盖：
  1. 内置规则模板引用的全部字段；
  2. 前端字段下拉表暴露的全部字段；
  3. 否定类操作符在字段缺失时的行为基线（会命中，是已知且刻意保留的语义）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fangyu_shared.rules.fields import CONTEXT_FIELDS, NULLABLE_FIELDS
from fangyu_shared.rules.operators import OPERATOR_NAMES, apply_operator, read_path
from fangyu_shared.schemas.decision import DecisionContext
from fangyu_shared.schemas.rule import ALLOWED_CONTEXT_ROOTS

from src.domain.profile.builder import ProfileBuilder

_UI_FIELDS_TS = (
    Path(__file__).resolve().parents[2] / "dashboard-ui" / "src" / "constants" / "ruleFields.ts"
)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _parse_ui_fields() -> set[str]:
    """从前端字段表解析出全部 field 取值路径。"""
    source = _UI_FIELDS_TS.read_text(encoding="utf-8")
    fields = set(re.findall(r"value: '([a-z]+\.[A-Za-z_]+)'", source))
    assert fields, "未能从 ruleFields.ts 解析出字段，正则或文件结构已变更"
    return fields


def _parse_ui_enum_options(source: str) -> dict[str, list[str]]:
    """解析出每个枚举字段的 options 取值列表。

    按 ``value: 'x.y'`` 切分成字段块后在块内找 options，不能跨块匹配——
    ``ip.ip`` 后面紧跟的是 ``ip.country`` 的 options，直接用非贪婪正则会错配。
    """
    starts = [(m.start(), m.group(1)) for m in re.finditer(r"value: '([a-z]+\.[A-Za-z_]+)'", source)]
    result: dict[str, list[str]] = {}
    for index, (offset, field) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(source)
        block = source[offset:end]
        match = re.search(r"options: \[(.*?)\]", block, re.S)
        if match:
            result[field] = re.findall(r"'([\w-]+)'", match.group(1))
    assert result, "未能从 ruleFields.ts 解析出枚举选项，文件结构已变更"
    return result


@pytest.fixture(scope="module")
def context() -> dict:
    """真实评估上下文，走与线上决策完全相同的构建路径。"""
    return ProfileBuilder().build(
        DecisionContext(
            appId=1,
            fingerprint="fp-contract",
            ip="8.8.8.8",
            userAgent=_BROWSER_UA,
            path="/",
            method="GET",
        )
    ).to_evaluation_context()


@pytest.fixture(scope="module")
def available_paths(context: dict) -> frozenset[str]:
    """上下文中真实可取值的字段路径全集。"""
    return frozenset(
        f"{ns}.{key}"
        for ns, values in context.items()
        if isinstance(values, dict)
        for key in values
    )


def test_context_covers_all_allowed_roots(context: dict) -> None:
    """schema 允许的每个命名空间都必须真实存在，否则整组字段全部落空。"""
    assert ALLOWED_CONTEXT_ROOTS <= context.keys()


def test_context_matches_shared_field_registry(available_paths: frozenset[str]) -> None:
    """网关真实上下文必须与 shared 的字段注册表一致。

    注册表是 admin 侧模板校验、前端字段表校验的共同基准；两者不能直接 import
    gateway（``src`` 包名冲突），只能依赖这份声明。此测试保证声明不说谎。
    """
    assert CONTEXT_FIELDS == available_paths, (
        f"注册表缺少: {sorted(available_paths - CONTEXT_FIELDS)}; "
        f"注册表多出: {sorted(CONTEXT_FIELDS - available_paths)}"
    )


def test_ui_fields_exist_in_context(available_paths: frozenset[str]) -> None:
    """前端下拉表暴露的字段必须都能取到值。

    界面上能选到的字段，运营会合理认为它可用。暴露取不到值的字段等于埋雷：
    规则能存能发布，但永远不命中，且无任何告警。
    """
    ui_fields = _parse_ui_fields()
    missing = ui_fields - available_paths
    assert not missing, (
        f"前端字段表暴露了上下文中不存在的字段，基于它们配置的规则永远不会命中: {sorted(missing)}"
    )


def test_ui_marks_nullable_fields_correctly() -> None:
    """前端对可空字段的 nullable 标注必须与注册表一致。

    标注驱动编辑器的误杀风险提示。漏标 → 运营配出「数据缺失即拦全站」的规则
    而无提示；多标 → 无意义的告警噪音，久而久之运营会忽略所有提示。
    """
    source = _UI_FIELDS_TS.read_text(encoding="utf-8")
    ui_fields = _parse_ui_fields()
    marked = {
        m.group(1)
        for m in re.finditer(
            r"value: '([a-z]+\.[A-Za-z_]+)'[^}]*?nullable: true", source, re.S
        )
    }
    expected = NULLABLE_FIELDS & ui_fields
    assert marked == expected, (
        f"前端漏标 nullable: {sorted(expected - marked)}; 多标: {sorted(marked - expected)}"
    )


def test_ui_operators_are_registered() -> None:
    """前端 OPERATOR_LABELS 的键必须与后端实现表一致。"""
    source = _UI_FIELDS_TS.read_text(encoding="utf-8")
    block = re.search(
        r"OPERATOR_LABELS: Record<string, string> = \{(.*?)\n\}", source, re.S
    )
    assert block is not None, "未能定位 OPERATOR_LABELS 定义"
    ui_ops = set(re.findall(r"^\s*(\w+):", block.group(1), re.M))
    assert ui_ops == set(OPERATOR_NAMES), (
        f"前端仅后端有: {sorted(set(OPERATOR_NAMES) - ui_ops)}; "
        f"后端仅前端有: {sorted(ui_ops - set(OPERATOR_NAMES))}"
    )


def test_ui_enum_options_have_chinese_labels() -> None:
    """枚举选项必须有中文文案，否则运营在下拉里只能看到原始英文值。

    豁免国家码、设备品牌、HTTP 方法：ISO 3166 码、厂商名、HTTP 动词本身
    就是通用标识，加中文只会让下拉变长。
    """
    source = _UI_FIELDS_TS.read_text(encoding="utf-8")
    labelled = set(re.findall(r"^\s*'([a-z_]+(?:\.[A-Za-z_]+)*)\.(\w+)':", source, re.M))
    labelled_keys = {f"{prefix}.{value}" for prefix, value in labelled}

    exempt = {"ip.country", "ua.brand", "request.method"}
    shared_prefix = {"ua.crawler_category": "crawler_category", "intel.crawler_category": "crawler_category"}

    missing: list[str] = []
    for field, options in _parse_ui_enum_options(source).items():
        if field in exempt:
            continue
        prefix = shared_prefix.get(field, field)
        missing += [f"{prefix}.{opt}" for opt in options if f"{prefix}.{opt}" not in labelled_keys]

    assert not missing, f"以下枚举选项缺少中文文案，运营只能看到原始英文值: {sorted(set(missing))}"


def test_datetime_fields_are_json_serialized(context: dict) -> None:
    """时间字段必须是字符串。

    若为 datetime 对象，contains / startswith / regex 等字符串操作符
    对其一律返回 False，相关条件静默落空。
    """
    for path in ("device.firstSeenAt", "device.lastSeenAt", "ip.lastSeenAt"):
        value = read_path(context, path)
        assert isinstance(value, str), f"{path} 应为 ISO 字符串，实际为 {type(value).__name__}"
    # 整个上下文可 JSON 序列化，保证能原样回传给前端试跑展示
    json.dumps(context)


def test_request_namespace_not_overridable_by_client() -> None:
    """客户端 extra 不得覆盖 request 固定键。

    若能覆盖，攻击者传 extra={"path": "/safe"} 即可让全部路径类规则失效。
    """
    snapshot = ProfileBuilder().build(
        DecisionContext(
            appId=1,
            fingerprint="fp",
            ip="8.8.8.8",
            userAgent=_BROWSER_UA,
            path="/admin/users",
            method="POST",
            extra={"path": "/safe", "method": "GET", "has_referer": True},
        )
    )
    ctx = snapshot.to_evaluation_context()
    assert ctx["request"]["path"] == "/admin/users"
    assert ctx["request"]["method"] == "POST"
    assert ctx["request"]["has_referer"] is False


@pytest.mark.parametrize(
    ("op", "expected_value"),
    [
        ("not_in", ["CN"]),
        ("not_in_ci", ["CN"]),
        ("asn_not_in", [4134]),
        ("cidr_list_not_in", ["10.0.0.0/8"]),
        ("neq", "CN"),
    ],
)
def test_negative_operators_match_on_missing_value(op: str, expected_value: object) -> None:
    """否定类操作符在取值为空时**会命中**，这是刻意保留的语义。

    「非白名单国家一律拦截」需要这个行为才能表达。代价是 MMDB 未加载时
    这类规则会拦下全部流量，因此前端对可空字段 + 否定操作符的组合给出
    风险提示，模板也显式加了「字段不等于空」的前置条件。
    此测试锁定行为基线，改动时必须同步评估上述两处。
    """
    assert apply_operator(op, None, expected_value) is True


def test_not_contains_does_not_match_on_missing_value() -> None:
    """not_contains 是唯一例外：取值为空或非字符串时不命中。

    它常被用在数值/布尔字段上（前端 STR_OPS 里就有），若沿用其他否定
    操作符的 fail-open 语义，会导致条件恒成立——配上 deny 就是放开阻断。
    """
    assert apply_operator("not_contains", None, "evil") is False
    assert apply_operator("not_contains", False, "evil") is False
    assert apply_operator("not_contains", 0, "evil") is False
    # 对真实字符串仍按预期工作
    assert apply_operator("not_contains", "abc", "x") is True
    assert apply_operator("not_contains", "abc", "b") is False
