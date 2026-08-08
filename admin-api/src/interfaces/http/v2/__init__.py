"""Admin API v2 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from .access_logs import router as access_logs_router
from .analytics import router as analytics_router
from .api_keys import router as api_keys_router
from .applications import router as applications_router
from .apps import router as apps_router
from .audit_logs import router as audit_logs_router
from .auth import router as auth_router
from .bans import router as bans_router
from .clock import router as clock_router, global_router as clock_global_router
from .diagnostics import router as diagnostics_router
from .health import router as health_router
from .page_resource_templates import router as page_resource_templates_router
from .page_resources import router as page_resources_router, global_router as page_resources_global_router
from .permissions import router as permissions_router
from .roles import router as roles_router
from .rule_templates import router as rule_templates_router
from .rules import router as rules_router, global_router as rules_global_router
from .scoring import router as scoring_router
from .sites import router as sites_router
from .threat_intel import router as threat_intel_router
from .users import router as users_router
from .intelligence import router as intelligence_router
from .whitelist import router as whitelist_router, global_router as whitelist_global_router

v2_router = APIRouter(prefix="/v2")

v2_router.include_router(auth_router)
v2_router.include_router(users_router)
v2_router.include_router(api_keys_router)
v2_router.include_router(roles_router)
v2_router.include_router(permissions_router)
v2_router.include_router(applications_router)
v2_router.include_router(sites_router)
v2_router.include_router(apps_router)
# 与 apps_router 同前缀 /sites，但路径带静态后缀 integration-diagnostics，
# 不会与 /sites/{site_id} 冲突
v2_router.include_router(diagnostics_router)
v2_router.include_router(rules_router)
v2_router.include_router(rules_global_router)
v2_router.include_router(rule_templates_router)
v2_router.include_router(threat_intel_router)
v2_router.include_router(intelligence_router)
v2_router.include_router(clock_router)
v2_router.include_router(clock_global_router)
v2_router.include_router(bans_router)
v2_router.include_router(whitelist_router)
v2_router.include_router(whitelist_global_router)
v2_router.include_router(analytics_router)
v2_router.include_router(access_logs_router)
v2_router.include_router(audit_logs_router)
# 先于 page_resources 注册：/page-resources/templates 是静态路径，
# 必须排在同前缀的 /{resource_id} 参数化路由之前，否则会被后者吞掉
v2_router.include_router(page_resource_templates_router)
v2_router.include_router(page_resources_router)
v2_router.include_router(page_resources_global_router)
v2_router.include_router(scoring_router)

# 健康/就绪不带前缀
v2_router.include_router(health_router)

__all__ = ["v2_router"]
