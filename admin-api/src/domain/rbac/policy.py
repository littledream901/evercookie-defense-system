"""RBAC 策略决策。

保证权限判断只在此处发生，方便测试与审计。
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.rbac.entities import Role


@dataclass(frozen=True, slots=True)
class PermissionContext:
    user_id: int
    role_names: frozenset[str]
    role_permissions: frozenset[str]

    def has(self, code: str) -> bool:
        return (
            code in self.role_permissions
            or f"{code.split('.', 1)[0]}.*" in self.role_permissions
            or "*" in self.role_permissions
        )


class PermissionPolicy:
    @staticmethod
    def build_context(user_id: int, roles: list[Role]) -> PermissionContext:
        perms: set[str] = set()
        names: set[str] = set()
        for role in roles:
            names.add(role.name)
            perms.update(role.permissions)
        return PermissionContext(
            user_id=user_id,
            role_names=frozenset(names),
            role_permissions=frozenset(perms),
        )

    @staticmethod
    def ensure(context: PermissionContext, code: str) -> None:
        if not context.has(code):
            from fangyu_shared.exceptions import PermissionDeniedException

            raise PermissionDeniedException(
                f"缺少权限: {code}",
                details={"required": code},
            )
