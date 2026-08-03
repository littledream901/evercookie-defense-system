"""Admin API v1 路由聚合（MMDB 管理）。"""

from __future__ import annotations

from fastapi import APIRouter

from .mmdb import router as mmdb_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(mmdb_router)

__all__ = ["v1_router"]
