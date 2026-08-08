"""用户 API Key 管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse

from src.application.services.api_key_service import ApiKeyService
from src.infrastructure.repositories.api_key_repository import ApiKeyRepository
from src.interfaces.http.dependencies import get_current_user_id, get_db_session

from .schemas import ApiKeyCreateRequest, ApiKeyCreatedResponse, ApiKeySchema

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def get_api_key_service(session=Depends(get_db_session)) -> ApiKeyService:
    return ApiKeyService(api_key_repo=ApiKeyRepository(session))


@router.post(
    "",
    response_model=SuccessResponse[ApiKeyCreatedResponse],
    status_code=201,
)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    user_id: int = Depends(get_current_user_id),
    service: ApiKeyService = Depends(get_api_key_service),
) -> SuccessResponse[ApiKeyCreatedResponse]:
    """创建 API Key。"""
    model, api_key = await service.create_api_key(user_id=user_id, name=payload.name)
    
    key_schema = ApiKeySchema(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        key_prefix=model.key_prefix,
        last_used_at=model.last_used_at,
        status=model.status,
        created_at=model.created_at,
    )
    
    return SuccessResponse(data=ApiKeyCreatedResponse(key=key_schema, api_key=api_key))


@router.get(
    "",
    response_model=SuccessResponse[list[ApiKeySchema]],
)
async def list_api_keys(
    user_id: int = Depends(get_current_user_id),
    service: ApiKeyService = Depends(get_api_key_service),
) -> SuccessResponse[list[ApiKeySchema]]:
    """列出当前用户的所有 API Key。"""
    models = await service.list_user_keys(user_id)
    
    keys = [
        ApiKeySchema(
            id=m.id,
            user_id=m.user_id,
            name=m.name,
            key_prefix=m.key_prefix,
            last_used_at=m.last_used_at,
            status=m.status,
            created_at=m.created_at,
        )
        for m in models
    ]
    
    return SuccessResponse(data=keys)


@router.delete(
    "/{key_id}",
    response_model=SuccessResponse[None],
)
async def delete_api_key(
    key_id: int,
    user_id: int = Depends(get_current_user_id),
    service: ApiKeyService = Depends(get_api_key_service),
) -> SuccessResponse[None]:
    """删除 API Key。"""
    await service.delete_api_key(key_id=key_id, user_id=user_id)
    return SuccessResponse(data=None)
