"""V2 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter

from src.interfaces.http.v2.decide import router as decide_router
from src.interfaces.http.v2.health import router as health_router
from src.interfaces.http.v2.rule_test import router as rule_test_router
from src.interfaces.http.v2.sdk import router as sdk_router
from src.interfaces.http.v2.challenge import router as challenge_router

v2_router = APIRouter(prefix="/v2")
v2_router.include_router(decide_router)
v2_router.include_router(rule_test_router)
v2_router.include_router(sdk_router)
v2_router.include_router(health_router)
v2_router.include_router(challenge_router)

__all__ = ["v2_router"]
