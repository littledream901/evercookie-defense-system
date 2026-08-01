"""处置三层模型与解析器测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fangyu_shared.schemas.disposition import (
    ChallengeKind,
    Disposition,
    Mechanism,
    Target,
    TargetKind,
    Verdict,
    allow,
    challenge,
    deny,
    not_found,
    observe,
    redirect,
    serve_alt,
)
from fangyu_shared.schemas.target_render import render_target

from src.domain.decision.disposition import (
    SYSTEM_DEFAULT_DISPOSITION,
    DecidedBy,
    DispositionResolver,
)


# ---------- 工厂预设 ----------
def test_allow_preset() -> None:
    d = allow()
    assert d.verdict == Verdict.TRUSTED
    assert d.mechanism == Mechanism.PASS
    assert d.effective_status == 200
    assert d.is_terminal is False


def test_observe_uses_shorter_ttl_than_allow() -> None:
    # 观察态需要更频繁刷新，缓存必须比纯放行短
    assert observe().ttl_seconds < allow().ttl_seconds


def test_deny_and_not_found_status() -> None:
    assert deny().effective_status == 403
    assert not_found().effective_status == 404
    assert deny().verdict == Verdict.HOSTILE
    assert not_found().is_terminal is True


def test_challenge_carries_kind() -> None:
    d = challenge(ChallengeKind.JS)
    assert d.challenge_kind == ChallengeKind.JS
    assert d.is_terminal is True


def test_redirect_permanent_vs_temporary() -> None:
    assert redirect("https://a.example/x").effective_status == 302
    assert redirect("https://a.example/x", permanent=True).effective_status == 301


def test_serve_alt_uses_page_resource_target() -> None:
    d = serve_alt("/alt.html")
    assert d.mechanism == Mechanism.SERVE_ALT
    assert d.target.kind == TargetKind.PAGE_RESOURCE
    assert d.effective_status == 200


# ---------- 语义校验：非法组合必须构造失败 ----------
def test_redirect_without_url_rejected() -> None:
    with pytest.raises(ValidationError):
        Disposition(verdict=Verdict.SUSPECT, mechanism=Mechanism.REDIRECT)


def test_challenge_without_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        Disposition(verdict=Verdict.SUSPECT, mechanism=Mechanism.CHALLENGE)


def test_challenge_kind_on_non_challenge_rejected() -> None:
    with pytest.raises(ValidationError):
        Disposition(
            verdict=Verdict.TRUSTED,
            mechanism=Mechanism.PASS,
            challengeKind=ChallengeKind.CAPTCHA,
        )


def test_url_target_requires_url() -> None:
    with pytest.raises(ValidationError):
        Target(kind=TargetKind.URL)


def test_explicit_status_overrides_mechanism_default() -> None:
    d = Disposition(
        verdict=Verdict.HOSTILE,
        mechanism=Mechanism.DENY,
        target=Target(kind=TargetKind.STATUS_ONLY, httpStatus=451),
    )
    assert d.effective_status == 451


# ---------- 目标渲染 ----------
def test_render_placeholders() -> None:
    out = render_target(
        "https://{host}/verify?from={path}",
        visit_url="https://shop.example/cart?id=9",
    )
    assert out == "https://shop.example/verify?from=/cart"


def test_render_keeps_relative_path() -> None:
    assert render_target("/safe.html", visit_url="https://a.example/x") == "/safe.html"


def test_render_rejects_javascript_scheme() -> None:
    # 占位符值来自请求，必须做协议白名单，否则可产出 XSS 载荷
    assert render_target("javascript:alert(1)") is None


def test_render_rejects_data_scheme() -> None:
    assert render_target("data:text/html;base64,AAAA") is None


def test_render_none_and_blank() -> None:
    assert render_target(None) is None
    assert render_target("   ") is None


def test_render_hash_route_path() -> None:
    out = render_target("{path}", visit_url="https://a.example/#/detail?id=1")
    assert out == "/detail"


# ---------- 解析器溯源 ----------
def test_from_rule_records_source() -> None:
    r = DispositionResolver.from_rule(deny(), rule_id=7, rule_name="block-cn")
    assert r.decided_by == DecidedBy.DECISION_RULE
    assert r.rule_id == 7
    assert "block-cn" in r.explain


def test_from_group_no_match_records_group() -> None:
    r = DispositionResolver.from_group_no_match(deny(), group_name="office-allowlist")
    assert r.decided_by == DecidedBy.GROUP_NO_MATCH
    assert "office-allowlist" in r.explain


def test_from_threat_intel_and_security() -> None:
    assert (
        DispositionResolver.from_threat_intel(deny(), reason="ti").decided_by
        == DecidedBy.THREAT_INTEL
    )
    assert (
        DispositionResolver.from_security(not_found(), reason="tor").decided_by
        == DecidedBy.SECURITY
    )


def test_fallback_prefers_app_default() -> None:
    app_default = observe()
    r = DispositionResolver.fallback(app_default)
    assert r.decided_by == DecidedBy.APP_DEFAULT
    assert r.disposition is app_default


def test_fallback_to_system_default() -> None:
    r = DispositionResolver.fallback(None)
    assert r.decided_by == DecidedBy.SYSTEM_DEFAULT
    # 兜底放行而非拦截：兜底被触发说明规则未覆盖，拦截会造成大面积误伤
    assert r.disposition.mechanism == Mechanism.PASS
    assert SYSTEM_DEFAULT_DISPOSITION.verdict == Verdict.TRUSTED
