"""Admin v2 HTTP 层 DTO。

只承担 request/response 序列化职责，业务对象仍由 domain 层持有。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from fangyu_shared.clock.limits import DEFAULT_BAN_SECONDS, MAX_BAN_SECONDS
from fangyu_shared.clock.windows import ClockDimension
from fangyu_shared.schemas.common import BaseSchema, PageRequest
from fangyu_shared.schemas.disposition import Disposition
from fangyu_shared.schemas.rule import (
    DecisionRule,
    GroupMode,
    RuleCondition,
    RuleKind,
    RulePriority,
)


# ---------- Auth ----------
class LoginRequest(BaseSchema):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseSchema):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseSchema):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenPairSchema(BaseSchema):
    access_token: str
    refresh_token: str
    expires_in: int


class UserBriefSchema(BaseSchema):
    id: int
    username: str
    email: str
    display_name: str
    status: str
    role_ids: list[int] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LoginResponse(BaseSchema):
    user: UserBriefSchema
    tokens: TokenPairSchema
    role_names: list[str]
    permissions: list[str]
    password_change_required: bool = False


class CurrentUserResponse(BaseSchema):
    user: UserBriefSchema
    role_names: list[str]
    permissions: list[str]


# ---------- User ----------
class UserListRequest(PageRequest):
    keyword: str | None = None
    status: Literal["active", "disabled", "locked"] | None = None


class UserCreateRequest(BaseSchema):
    username: str = Field(min_length=2, max_length=64)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=128)
    role_ids: list[int] = Field(default_factory=list)


class UserUpdateRequest(BaseSchema):
    email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str | None = None
    status: Literal["active", "disabled", "locked"] | None = None


class UserResetPasswordRequest(BaseSchema):
    new_password: str = Field(min_length=8, max_length=128)


class UserAssignRolesRequest(BaseSchema):
    role_ids: list[int] = Field(default_factory=list)


# ---------- Role / Permission ----------
class RoleSchema(BaseSchema):
    id: int
    name: str
    description: str
    is_system: bool
    permissions: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoleCreateRequest(BaseSchema):
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseSchema):
    description: str | None = None
    permissions: list[str] | None = None


class PermissionSchema(BaseSchema):
    code: str
    description: str


class PermissionUpsertRequest(BaseSchema):
    code: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=255)


# ---------- Application ----------
class AppSchema(BaseSchema):
    id: int
    name: str
    api_key: str
    owner_user_id: int
    status: str
    description: str
    domains: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AppListRequest(PageRequest):
    keyword: str | None = None
    status: Literal["active", "paused", "archived"] | None = None
    owner_id: int | None = None


class AppCreateRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    domains: list[str] = Field(default_factory=list)


class AppUpdateRequest(BaseSchema):
    name: str | None = None
    description: str | None = None
    domains: list[str] | None = None
    status: Literal["active", "paused", "archived"] | None = None


# ---------- Rule ----------
class RuleListRequest(PageRequest):
    keyword: str | None = None
    status: Literal["draft", "published", "disabled", "archived"] | None = None


class RuleUpsertRequest(BaseSchema):
    """规则新建/编辑请求。

    ``kind=decision`` 时必须提供 ``disposition``；``kind=scoring`` 时必须提供
    ``weight``。两者互斥，由校验器强制。
    """

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    kind: RuleKind = RuleKind.DECISION
    priority: RulePriority = RulePriority.NORMAL
    conditions: list[RuleCondition] = Field(..., min_length=1)
    match_all: bool = Field(default=True, alias="matchAll")
    group: str | None = Field(default=None, max_length=64)
    tags: list[str] = Field(default_factory=list)
    weight: int | None = Field(default=None, ge=-1000, le=1000)
    disposition: Disposition | None = None

    @model_validator(mode="after")
    def _check_kind_fields(self) -> RuleUpsertRequest:
        if self.kind == RuleKind.DECISION:
            if self.disposition is None:
                raise ValueError("kind=decision 必须提供 disposition")
            if self.weight is not None:
                raise ValueError("kind=decision 不接受 weight（命中即终止，权重无意义）")
        else:
            if self.weight is None:
                raise ValueError("kind=scoring 必须提供 weight")
            if self.disposition is not None:
                raise ValueError("kind=scoring 不接受 disposition（打分规则不做处置决策）")
        return self


class RuleRollbackRequest(BaseSchema):
    target_version: int = Field(ge=1)


class RuleGroupUpsertRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=64)
    mode: GroupMode = GroupMode.BLOCKLIST
    priority: RulePriority = RulePriority.NORMAL
    enabled: bool = True
    on_no_match: Disposition | None = Field(default=None, alias="onNoMatch")


class RuleTestRequest(BaseSchema):
    rule: DecisionRule
    sample_context: dict = Field(default_factory=dict)


# ---------- Analytics ----------
class AnalyticsBaseRequest(BaseSchema):
    app_id: int
    start: datetime
    end: datetime
    filters: dict[str, str] = Field(default_factory=dict)


class TimelineRequest(AnalyticsBaseRequest):
    granularity: Literal["minute", "hour", "day"] = "hour"


class TopEntityRequest(AnalyticsBaseRequest):
    dimension: Literal["ip", "device", "country"] = "ip"
    limit: int = Field(default=20, ge=1, le=100)


# ---------- Clock 频控 ----------
class ClockLimitsUpdateRequest(BaseSchema):
    """频控阈值更新请求。

    这里刻意不复用 ``ClockLimits``：它带 ``app_id``，而 app_id 来自路径参数，
    body 里再出现一次就有了两个真相来源，不一致时该信谁没有明确答案。
    窗口名与阈值范围的校验交给 service 层构造 ``ClockLimits`` 时统一执行，
    避免同一套规则在 DTO 和领域对象里写两遍。
    """

    enabled: bool = True
    windows: dict[str, int] = Field(default_factory=dict)
    ban_seconds: int = Field(default=DEFAULT_BAN_SECONDS, alias="banSeconds", ge=0)
    ban_enabled: bool = Field(default=True, alias="banEnabled")


class ClockBanRequest(BaseSchema):
    """手工封禁请求。"""

    dimension: ClockDimension
    value: str = Field(min_length=1, max_length=128)
    seconds: int = Field(default=DEFAULT_BAN_SECONDS, ge=1, le=MAX_BAN_SECONDS)
    reason: str = Field(default="manual", max_length=128)
