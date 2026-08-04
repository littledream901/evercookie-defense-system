"""Admin API HTTP 层依赖注入。

所有 v2 路由通过这里获取 Session、缓存、服务实例与当前登录用户。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fangyu_shared.clickhouse_manager import ClickHouseClient, get_clickhouse
from fangyu_shared.exceptions import AuthenticationException
from fangyu_shared.redis_manager import RedisManager
from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.analytics_service import AnalyticsService
from src.application.services.app_service import AppService
from src.application.services.audit_service import AuditService
from src.application.services.auth_service import AuthService
from src.application.services.clock_service import ClockService
from src.application.services.page_resource_service import PageResourceService
from src.application.services.reputation_sync_service import ReputationSyncService
from src.application.services.role_service import RoleService
from src.application.services.rule_service import RuleService
from src.application.services.scoring_service import ScoringService
from src.application.services.intel_service import IntelService
from src.application.services.threat_intel_service import ThreatIntelService
from src.application.services.user_service import UserService
from src.application.services.whitelist_service import WhitelistService
from src.config import AdminSettings, get_settings
from src.domain.rbac.policy import PermissionContext
from src.domain.user.password import PasswordService
from fangyu_shared.cache.profile_cache import ProfileCache as SharedProfileCache
from src.infrastructure.cache.app_key_sync import AppKeyRedisSync
from src.infrastructure.cache.page_resource_cache import PageResourceCache
from src.infrastructure.cache.permission_cache import PermissionCache
from src.infrastructure.cache.rule_cache import RuleCache
from src.infrastructure.clickhouse.analytics_query import AnalyticsQueryService
from src.infrastructure.clock_sync import ClockSync
from src.infrastructure.database import Database
from src.infrastructure.repositories.app_repository import AppRepository
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.infrastructure.repositories.page_resource_repository import PageResourceRepository
from src.infrastructure.repositories.rbac_repository import RbacRepository
from src.infrastructure.repositories.rule_repository import RuleAdminRepository
from src.infrastructure.repositories.scoring_repository import ScoringRepository
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.reputation_intel_feedback import ReputationIntelFeedback
from src.infrastructure.scoring_sync import ScoringSync
from src.infrastructure.whitelist_sync import WhitelistSync


# ---------- 基础设施 ----------
async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with Database.session() as session:
        yield session


def get_redis() -> Redis:
    return RedisManager.get_client()


def get_settings_dep() -> AdminSettings:
    return get_settings()


# ---------- 缓存 ----------
def get_permission_cache(
    redis: Redis = Depends(get_redis),
    settings: AdminSettings = Depends(get_settings_dep),
) -> PermissionCache:
    return PermissionCache(redis, ttl=settings.permission_cache_ttl)


def get_rule_cache(redis: Redis = Depends(get_redis)) -> RuleCache:
    return RuleCache(redis)


def get_app_key_sync(
    redis: Redis = Depends(get_redis),
    settings: AdminSettings = Depends(get_settings_dep),
) -> AppKeyRedisSync:
    return AppKeyRedisSync(
        redis,
        key_prefix=settings.app_key_redis_prefix,
        ttl_seconds=settings.app_key_redis_ttl_seconds or None,
    )


# ---------- Repository ----------
def get_user_repo(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    return UserRepository(session)


def get_rbac_repo(session: AsyncSession = Depends(get_db_session)) -> RbacRepository:
    return RbacRepository(session)


def get_app_repo(session: AsyncSession = Depends(get_db_session)) -> AppRepository:
    return AppRepository(session)


def get_rule_repo(session: AsyncSession = Depends(get_db_session)) -> RuleAdminRepository:
    return RuleAdminRepository(session)


def get_password_service() -> PasswordService:
    return PasswordService()


def get_analytics_query_service(
    client: ClickHouseClient = Depends(get_clickhouse),
) -> AnalyticsQueryService:
    return AnalyticsQueryService(client)


# ---------- Service ----------
def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repo),
    rbac_repo: RbacRepository = Depends(get_rbac_repo),
    perm_cache: PermissionCache = Depends(get_permission_cache),
    password_service: PasswordService = Depends(get_password_service),
    settings: AdminSettings = Depends(get_settings_dep),
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        rbac_repo=rbac_repo,
        permission_cache=perm_cache,
        password_service=password_service,
        settings=settings,
    )


def get_user_service(
    user_repo: UserRepository = Depends(get_user_repo),
    rbac_repo: RbacRepository = Depends(get_rbac_repo),
    password_service: PasswordService = Depends(get_password_service),
    perm_cache: PermissionCache = Depends(get_permission_cache),
) -> UserService:
    return UserService(
        user_repo=user_repo,
        rbac_repo=rbac_repo,
        password_service=password_service,
        permission_cache=perm_cache,
    )


def get_role_service(
    rbac_repo: RbacRepository = Depends(get_rbac_repo),
    perm_cache: PermissionCache = Depends(get_permission_cache),
) -> RoleService:
    return RoleService(rbac_repo=rbac_repo, permission_cache=perm_cache)


def get_app_service(
    app_repo: AppRepository = Depends(get_app_repo),
    app_key_sync: AppKeyRedisSync = Depends(get_app_key_sync),
) -> AppService:
    return AppService(app_repo, app_key_sync=app_key_sync)


def get_audit_repo(session: AsyncSession = Depends(get_db_session)) -> AuditLogRepository:
    return AuditLogRepository(session)


def get_audit_service(
    repo: AuditLogRepository = Depends(get_audit_repo),
) -> AuditService:
    return AuditService(repo)


def get_rule_service(
    rule_repo: RuleAdminRepository = Depends(get_rule_repo),
    rule_cache: RuleCache = Depends(get_rule_cache),
) -> RuleService:
    return RuleService(rule_repo=rule_repo, rule_cache=rule_cache)


def get_analytics_service(
    query_service: AnalyticsQueryService = Depends(get_analytics_query_service),
) -> AnalyticsService:
    return AnalyticsService(query_service)


def get_threat_intel_service(
    session: AsyncSession = Depends(get_db_session),
) -> ThreatIntelService:
    return ThreatIntelService(session)


def get_intel_service(
    session: AsyncSession = Depends(get_db_session),
) -> IntelService:
    return IntelService(session)


def get_clock_service(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ClockService:
    return ClockService(session, ClockSync(redis))


def get_whitelist_service(
    redis: Redis = Depends(get_redis),
) -> WhitelistService:
    """白名单服务。不需要 DB session——白名单只存 Redis。"""
    return WhitelistService(WhitelistSync(redis))


def get_page_resource_repo(
    session: AsyncSession = Depends(get_db_session),
) -> PageResourceRepository:
    return PageResourceRepository(session)


def get_scoring_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ScoringRepository:
    return ScoringRepository(session)


def get_page_resource_cache(
    redis: Redis = Depends(get_redis),
) -> PageResourceCache:
    return PageResourceCache(redis)


def get_page_resource_service(
    resource_repo: PageResourceRepository = Depends(get_page_resource_repo),
    resource_cache: PageResourceCache = Depends(get_page_resource_cache),
) -> PageResourceService:
    return PageResourceService(
        resource_repo=resource_repo,
        resource_cache=resource_cache,
    )


def get_scoring_sync(redis: Redis = Depends(get_redis)) -> ScoringSync:
    return ScoringSync(redis)


def get_scoring_service(
    repo: ScoringRepository = Depends(get_scoring_repo),
    sync: ScoringSync = Depends(get_scoring_sync),
) -> ScoringService:
    return ScoringService(repo, sync)


# ---------- 认证与鉴权 ----------
async def get_current_user_id(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationException("缺少或格式错误的 Authorization 头")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationException("Token 为空")
    user_id = await auth_service.verify_token(token)
    request.state.current_user_id = user_id
    return user_id


async def get_current_permissions(
    user_id: int = Depends(get_current_user_id),
    auth_service: AuthService = Depends(get_auth_service),
) -> PermissionContext:
    return await auth_service.get_permission_context(user_id)


def get_reputation_sync_service(
    clickhouse: ClickHouseClient = Depends(get_clickhouse),
    redis: Redis = Depends(get_redis),
    intel_service: IntelService = Depends(get_intel_service),
) -> ReputationSyncService:
    return ReputationSyncService(
        clickhouse=clickhouse,
        profile_cache=SharedProfileCache(redis, ttl=86_400),
        # 手动触发时顺带把高风险 IP 沉淀进情报库；worker 侧没有 DB 依赖，
        # 这一步只能在 admin 完成。
        intel_feedback=ReputationIntelFeedback(intel_service),
    )


def require_permission(code: str):
    """路由级权限守卫工厂。

    使用: dependencies=[Depends(require_permission("rule.write"))]
    """

    async def _guard(
        user_id: int = Depends(get_current_user_id),
        auth_service: AuthService = Depends(get_auth_service),
    ) -> None:
        await auth_service.check_permission(user_id, code)

    return _guard
