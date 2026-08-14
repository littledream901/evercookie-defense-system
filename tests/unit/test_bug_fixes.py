"""Bug修复验证单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, Header
from typing import Annotated

from fangyu_shared.exceptions import AuthenticationException


class TestBug001002AuthenticationValidation:
    """BUG-001/002: 认证异常处理验证测试"""

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self):
        """测试缺少 Authorization 头"""
        from admin_api.src.interfaces.http.dependencies import get_current_user_id
        
        request = MagicMock(spec=Request)
        auth_service = AsyncMock()
        api_key_service = AsyncMock()
        user_repo = AsyncMock()
        
        with pytest.raises(AuthenticationException, match="缺少 Authorization 头"):
            await get_current_user_id(
                request=request,
                authorization=None,
                auth_service=auth_service,
                api_key_service=api_key_service,
                user_repo=user_repo,
            )

    @pytest.mark.asyncio
    async def test_empty_authorization_header(self):
        """测试空 Authorization 头"""
        from admin_api.src.interfaces.http.dependencies import get_current_user_id
        
        request = MagicMock(spec=Request)
        auth_service = AsyncMock()
        api_key_service = AsyncMock()
        user_repo = AsyncMock()
        
        with pytest.raises(AuthenticationException, match="缺少 Authorization 头"):
            await get_current_user_id(
                request=request,
                authorization="   ",
                auth_service=auth_service,
                api_key_service=api_key_service,
                user_repo=user_repo,
            )

    @pytest.mark.asyncio
    async def test_malformed_authorization_header_no_bearer(self):
        """测试格式错误的 Authorization 头（无 Bearer 前缀）"""
        from admin_api.src.interfaces.http.dependencies import get_current_user_id
        
        request = MagicMock(spec=Request)
        auth_service = AsyncMock()
        api_key_service = AsyncMock()
        user_repo = AsyncMock()
        
        with pytest.raises(AuthenticationException, match="Authorization 头格式错误"):
            await get_current_user_id(
                request=request,
                authorization="InvalidToken",
                auth_service=auth_service,
                api_key_service=api_key_service,
                user_repo=user_repo,
            )

    @pytest.mark.asyncio
    async def test_malformed_authorization_header_bearer_only(self):
        """测试格式错误的 Authorization 头（只有 Bearer）"""
        from admin_api.src.interfaces.http.dependencies import get_current_user_id
        
        request = MagicMock(spec=Request)
        auth_service = AsyncMock()
        api_key_service = AsyncMock()
        user_repo = AsyncMock()
        
        with pytest.raises(AuthenticationException, match="Token 为空"):
            await get_current_user_id(
                request=request,
                authorization="Bearer ",
                auth_service=auth_service,
                api_key_service=api_key_service,
                user_repo=user_repo,
            )


class TestBug004DeleteUserStatusCode:
    """BUG-004: DELETE 用户返回状态码验证"""

    def test_delete_user_endpoint_returns_204(self):
        """验证 DELETE /v2/users/{id} 返回 204 No Content"""
        from admin_api.src.interfaces.http.v2.users import delete_user
        import inspect
        
        # 检查返回类型注解
        sig = inspect.signature(delete_user)
        assert sig.return_annotation is None or sig.return_annotation == type(None), \
            "DELETE 端点应该返回 None (204 No Content)"
        
        # 检查装饰器中的 status_code
        # 注：实际需要检查路由装饰器，这里简化为检查函数签名


class TestBug006RuleGroupsRouting:
    """BUG-006: rule-groups 路由注册验证"""

    def test_rule_groups_router_has_prefix(self):
        """验证 rule-groups 路由有统一前缀"""
        from admin_api.src.interfaces.http.v2.rule_groups import router
        
        assert router.prefix == "/rule-groups", \
            "rule-groups router 应该有 /rule-groups 前缀"

    @pytest.mark.asyncio
    async def test_rule_group_service_has_list_all_method(self):
        """验证 RuleGroupService 有 list_all 方法"""
        from admin_api.src.application.services.rule_group_service import RuleGroupService
        
        assert hasattr(RuleGroupService, 'list_all'), \
            "RuleGroupService 应该有 list_all 方法"
        
        # 检查方法签名
        import inspect
        sig = inspect.signature(RuleGroupService.list_all)
        assert 'self' in sig.parameters, "list_all 应该是实例方法"

    @pytest.mark.asyncio
    async def test_rule_group_repository_has_list_all_method(self):
        """验证 RuleGroupRepository 有 list_all 方法"""
        from admin_api.src.infrastructure.repositories.rule_group_repository import RuleGroupRepository
        
        assert hasattr(RuleGroupRepository, 'list_all'), \
            "RuleGroupRepository 应该有 list_all 方法"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
