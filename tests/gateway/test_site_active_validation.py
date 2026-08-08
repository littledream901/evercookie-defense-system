"""测试站点激活状态验证功能。

验证场景：
1. 激活站点正常通过鉴权
2. 已停用站点被拒绝（返回 401）
3. 已删除站点（Redis 无映射）被拒绝
4. 旧格式数据（无 is_active 字段）默认允许通过（向后兼容）
"""

import orjson
import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from gateway_api.src.interfaces.http.middleware.app_key import AppKeyResolver


@pytest.fixture
async def redis_client(redis: Redis) -> Redis:
    """Redis 客户端 fixture。"""
    yield redis
    # 清理测试数据
    await redis.delete(
        "fangyu:app_keys:test_active_site",
        "fangyu:app_keys:test_inactive_site",
        "fangyu:app_keys:test_legacy_site",
        "fangyu:app_secrets:9001",
        "fangyu:app_secrets:9002",
        "fangyu:app_secrets:9003",
    )


@pytest.fixture
async def resolver(redis_client: Redis) -> AppKeyResolver:
    """AppKeyResolver 实例。"""
    return AppKeyResolver(redis_client, cache_ttl=0)  # 禁用缓存便于测试


async def test_active_site_allowed(redis_client: Redis, resolver: AppKeyResolver) -> None:
    """激活站点允许通过鉴权。"""
    # 写入激活站点映射
    site_key = "test_active_site"
    payload = {"app_id": 9001, "app_secret": "secret123", "is_active": True}
    await redis_client.set(f"fangyu:app_keys:{site_key}", orjson.dumps(payload))
    await redis_client.set("fangyu:app_secrets:9001", "secret123")
    
    # 验证解析成功
    credential = await resolver.resolve_credential(site_key)
    assert credential is not None
    assert credential.site_id == 9001
    assert credential.site_secret == "secret123"
    assert credential.is_active is True


async def test_inactive_site_rejected(redis_client: Redis, resolver: AppKeyResolver) -> None:
    """已停用站点拒绝通过鉴权。"""
    # 写入停用站点映射
    site_key = "test_inactive_site"
    payload = {"app_id": 9002, "app_secret": "secret456", "is_active": False}
    await redis_client.set(f"fangyu:app_keys:{site_key}", orjson.dumps(payload))
    
    # 验证解析成功但状态为 False
    credential = await resolver.resolve_credential(site_key)
    assert credential is not None
    assert credential.site_id == 9002
    assert credential.is_active is False


async def test_legacy_format_defaults_to_active(
    redis_client: Redis, resolver: AppKeyResolver
) -> None:
    """旧格式数据（无 is_active 字段）默认视为激活状态（向后兼容）。"""
    # 写入旧格式映射（无 is_active 字段）
    site_key = "test_legacy_site"
    payload = {"app_id": 9003, "app_secret": "secret789"}
    await redis_client.set(f"fangyu:app_keys:{site_key}", orjson.dumps(payload))
    
    # 验证解析成功且默认激活
    credential = await resolver.resolve_credential(site_key)
    assert credential is not None
    assert credential.site_id == 9003
    assert credential.is_active is True  # 默认激活


async def test_deleted_site_returns_none(resolver: AppKeyResolver) -> None:
    """已删除站点（Redis 无映射）返回 None。"""
    credential = await resolver.resolve_credential("nonexistent_site")
    assert credential is None


@pytest.mark.integration
async def test_inactive_site_e2e_rejection(
    client: AsyncClient, redis_client: Redis
) -> None:
    """端到端测试：停用站点的决策请求被拒绝。"""
    # 写入停用站点映射
    site_key = "test_e2e_inactive"
    payload = {"app_id": 9999, "app_secret": "e2e_secret", "is_active": False}
    await redis_client.set(f"fangyu:app_keys:{site_key}", orjson.dumps(payload))
    
    # 发送决策请求
    response = await client.post(
        "/v2/decide",
        headers={"X-App-Key": site_key},
        json={
            "context": {
                "clientIp": "1.2.3.4",
                "userAgent": "TestAgent",
                "visitUrl": "https://test.com",
            }
        },
    )
    
    # 验证返回 401
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "SITE_INACTIVE"
    assert "停用" in body["message"] or "删除" in body["message"]
    
    # 清理
    await redis_client.delete(f"fangyu:app_keys:{site_key}")
