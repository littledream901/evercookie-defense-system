"""RBAC 策略单元测试。"""
from __future__ import annotations

import pytest

from fangyu_shared.exceptions import PermissionDeniedException
from src.domain.rbac.entities import Role
from src.domain.rbac.policy import PermissionPolicy


def _make_role(name: str, perms: list[str]) -> Role:
    return Role(id=None, name=name, permissions=frozenset(perms))


class TestPermissionContext:
    def test_direct_code_match(self):
        ctx = PermissionPolicy.build_context(1, [_make_role("r1", ["user.read"])])
        assert ctx.has("user.read")
        assert not ctx.has("user.write")

    def test_wildcard_resource(self):
        ctx = PermissionPolicy.build_context(1, [_make_role("r1", ["user.*"])])
        assert ctx.has("user.read")
        assert ctx.has("user.write")
        assert not ctx.has("role.read")

    def test_star_wildcard(self):
        ctx = PermissionPolicy.build_context(1, [_make_role("super", ["*"])])
        assert ctx.has("anything.here")

    def test_multiple_roles_union(self):
        ctx = PermissionPolicy.build_context(
            1,
            [
                _make_role("a", ["user.read"]),
                _make_role("b", ["role.write"]),
            ],
        )
        assert ctx.has("user.read")
        assert ctx.has("role.write")
        assert "a" in ctx.role_names and "b" in ctx.role_names


class TestPermissionPolicyEnsure:
    def test_pass_when_has(self):
        ctx = PermissionPolicy.build_context(1, [_make_role("r", ["user.read"])])
        PermissionPolicy.ensure(ctx, "user.read")

    def test_raises_when_missing(self):
        ctx = PermissionPolicy.build_context(1, [_make_role("r", ["role.read"])])
        with pytest.raises(PermissionDeniedException) as excinfo:
            PermissionPolicy.ensure(ctx, "user.write")
        assert excinfo.value.details["required"] == "user.write"
        assert "user.write" in excinfo.value.message
