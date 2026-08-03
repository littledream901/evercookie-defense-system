"""内置规则模板的字段与语义契约测试。

模板是运营创建规则的起点：模板里的幽灵字段、错误操作符、缺失值误杀会
1:1 复制进生产规则。因此每条模板都必须能真实命中它声称要拦的场景。

字段合法性以 :mod:`fangyu_shared.rules.fields` 的注册表为基准，该注册表
在 gateway 侧有测试断言其与真实评估上下文完全一致。
"""

from __future__ import annotations

import pytest

from fangyu_shared.rules.fields import CONTEXT_FIELDS, has_null_risk
from fangyu_shared.rules.operators import OPERATOR_NAMES, evaluate_conditions
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile
from fangyu_shared.ua import parse_user_agent

from src.interfaces.http.v2.rule_templates import _TEMPLATES

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class _Cond:
    """模板条件的三元组视图，供 evaluate_conditions 消费。"""

    __slots__ = ("field", "op", "value")

    def __init__(self, raw: dict) -> None:
        self.field = raw["field"]
        self.op = raw["op"]
        self.value = raw["value"]


def _context(*, ua: str = _BROWSER_UA, path: str = "/", **ip_kwargs) -> dict:
    """复刻 ProfileSnapshot.to_evaluation_context() 的结构。

    不直接调用 gateway 的 ProfileBuilder：admin-api 与 gateway-api 都以
    ``src`` 为顶层包名，同一进程内不能都导入。字段一致性由注册表保证。
    """
    return {
        "device": DeviceProfile(fingerprint="fp").model_dump(by_alias=True, mode="json"),
        "ip": IpProfile(ip="8.8.8.8", **ip_kwargs).model_dump(by_alias=True, mode="json"),
        "ua": parse_user_agent(ua).to_dict(),
        "intel": {
            "matched": False,
            "risk_score": 0,
            "reasons": [],
            "crawler_category": None,
            "crawler_name": None,
            "is_legitimate_crawler": False,
        },
        "request": {
            "path": path,
            "method": "GET",
            "user_agent": ua,
            "referer": None,
            "session_id": None,
            "has_referer": False,
        },
    }


def _conds(template_id: str) -> list[_Cond]:
    tpl = next(t for t in _TEMPLATES if t.id == template_id)
    return [_Cond(c) for c in tpl.conditions]


def test_local_context_matches_field_registry() -> None:
    """本文件构造的上下文必须与注册表一致，否则后续断言没有意义。"""
    built = {
        f"{ns}.{key}"
        for ns, values in _context().items()
        for key in values
    }
    assert built == CONTEXT_FIELDS, (
        f"缺少: {sorted(CONTEXT_FIELDS - built)}; 多出: {sorted(built - CONTEXT_FIELDS)}"
    )


@pytest.mark.parametrize("template", _TEMPLATES, ids=lambda t: t.id)
def test_template_fields_are_resolvable(template) -> None:
    """模板字段必须能取到值，否则条件永远不命中。"""
    bad = [c["field"] for c in template.conditions if c["field"] not in CONTEXT_FIELDS]
    assert not bad, f"模板 {template.id} 引用了不存在的字段，条件永远不会命中: {bad}"


@pytest.mark.parametrize("template", _TEMPLATES, ids=lambda t: t.id)
def test_template_operators_are_implemented(template) -> None:
    """模板操作符必须已实现，未实现的会被 apply_operator 静默判为 False。"""
    bad = [c["op"] for c in template.conditions if c["op"] not in OPERATOR_NAMES]
    assert not bad, f"模板 {template.id} 使用了未实现的操作符: {bad}"


@pytest.mark.parametrize("template", _TEMPLATES, ids=lambda t: t.id)
def test_template_guards_null_risk(template) -> None:
    """用了「缺失即命中」组合的模板，必须自带排除空值的前置条件。

    否则 MMDB 未加载或内网地址等场景下，规则会命中并施加处置——对
    ``deny`` 类模板就是全站阻断。
    """
    risky = [
        c["field"] for c in template.conditions if has_null_risk(c["field"], c["op"])
    ]
    if not risky:
        return
    guarded = {
        c["field"]
        for c in template.conditions
        if c["op"] == "neq" and c["value"] is None
    }
    unguarded = set(risky) - guarded
    assert not unguarded, (
        f"模板 {template.id} 对可空字段 {sorted(unguarded)} 用了否定操作符但未排除空值，"
        f"数据缺失时会命中并施加 {template.disposition.mechanism.value if template.disposition else '打分'}"
    )


def test_allow_country_only_does_not_block_on_missing_geo() -> None:
    """仅放行指定国家：地理数据缺失时不得阻断。"""
    conds = _conds("allow-country-only")
    assert evaluate_conditions(conds, _context(country="CN"), match_all=True) is False
    assert evaluate_conditions(conds, _context(country="US"), match_all=True) is True
    # MMDB 未加载 / 内网地址 → country 为 None，必须放行而非拦全站
    assert evaluate_conditions(conds, _context(), match_all=True) is False


def test_challenge_new_device_distinguishes_new_from_returning() -> None:
    """新设备挑战：必须能真正区分新老设备。"""
    conds = _conds("challenge-new-device")
    assert evaluate_conditions(conds, _context(), match_all=True) is True

    returning = _context()
    returning["device"]["totalRequests"] = 42
    assert evaluate_conditions(conds, returning, match_all=True) is False


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/admin", True),
        ("/admin/", True),
        ("/admin/users", True),
        ("/checkout", True),
        ("/checkout/pay", True),
        ("/administrator", False),
        ("/checkouts", False),
        ("/public", False),
    ],
)
def test_path_block_covers_subpaths(path: str, expected: bool) -> None:
    """敏感路径阻断：必须覆盖子路径，且不误伤前缀相似的路径。

    原实现用 in（精确相等），只能挡 /admin 本身，/admin/users 直接放行。
    """
    conds = _conds("path-block")
    assert evaluate_conditions(conds, _context(path=path), match_all=True) is expected


def test_normal_browser_hits_no_blocking_template() -> None:
    """普通浏览器请求不应命中任何阻断类模板。

    命中说明模板条件过宽，会造成大面积误杀。
    """
    ctx = _context()
    blocking = {"deny", "not_found", "serve_alt", "redirect"}
    hits = [
        t.id
        for t in _TEMPLATES
        if t.disposition is not None
        and t.disposition.mechanism.value in blocking
        and evaluate_conditions([_Cond(c) for c in t.conditions], ctx, match_all=True)
    ]
    assert not hits, f"普通浏览器请求命中了阻断类模板，条件过宽: {hits}"
