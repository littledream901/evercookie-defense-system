"""Admin API v2 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from .access_logs import router as access_logs_router
from .analytics import router as analytics_router
from .apps import router as apps_router
from .audit_logs import router as audit_logs_router
from .auth import router as auth_router
from .clock import router as clock_router
from .health import router as health_router
from .permissions import router as permissions_router
from .roles import router as roles_router
from .rule_templates import router as rule_templates_router
from .rules import router as rules_router
from .threat_intel import router as threat_intel_router
from .users import router as users_router

v2_router = APIRouter(prefix="/v2")

v2_router.include_router(auth_router)
v2_router.include_router(users_router)
v2_router.include_router(roles_router)
v2_router.include_router(permissions_router)
v2_router.include_router(apps_router)
v2_router.include_router(rules_router)
v2_router.include_router(rule_templates_router)
v2_router.include_router(threat_intel_router)
v2_router.include_router(clock_router)
v2_router.include_router(analytics_router)
v2_router.include_router(access_logs_router)
v2_router.include_router(audit_logs_router)

# 健康/就绪不带前缀
v2_router.include_router(health_router)

__all__ = ["v2_router"]
