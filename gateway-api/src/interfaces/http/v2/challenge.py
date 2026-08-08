"""挑战校验接口。

客户端完成挑战（captcha / js_challenge）后，携带 challengeToken + answer 提交答案。
Gateway 校验 token 签名与答案正确性，通过后签发通行凭据（写 Redis），
客户端下次请求携带凭据即可短路决策流水线。

凭据格式：使用 NonceStore 机制，key = `fy:challenge_pass:{app_id}:{fingerprint}`，
value = verdict（"trusted"），TTL = token 中的 ttl。

为什么不直接写 DecisionCache：
- DecisionCache 键位依赖完整的 DecisionContext（包括 path、visit_url 等），
  而挑战完成时客户端不一定在原始 path 上。
- 挑战通行是**访客级**的，而非**请求级**，应跨路径生效。
- 轻量 Redis string 比 DecisionCache 的序列化开销更低。

安全设计：
- token 签名校验：防伪造
- nonce 一次性：防重放（同一 token 只能提交一次答案）
- fingerprint 绑定：防跨访客盗用
- app_id 绑定：防跨租户盗用
- 答案校验：captcha 由第三方服务校验，js_challenge 验证客户端计算结果
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from fangyu_shared.challenge_token import verify_challenge_token
from fangyu_shared.exceptions import AuthenticationException, ValidationException
from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.common import SuccessResponse
from fangyu_shared.schemas.disposition import ChallengeKind

from src.infrastructure.cache.nonce_store import NonceStore
from src.interfaces.http.dependencies import get_app_key_resolver, get_nonce_store
from src.interfaces.http.middleware.app_key import ResolvedAppKey, require_app_key

router = APIRouter(prefix="/challenge", tags=["challenge"])
_logger = get_logger("gateway.challenge")


class ChallengeVerifyRequest(BaseModel):
    """挑战答案提交请求。
    
    Note:
        app_id 字段实际是站点主键（Site.id），这是
    """

    site_id: int = Field(..., alias="siteId", ge=1)
    """站点主键（Site.id）"""
    fingerprint: str = Field(..., min_length=1, max_length=256)
    challenge_token: str = Field(..., alias="challengeToken", min_length=1)
    answer: str = Field(..., min_length=1, max_length=4096)
    """captcha：第三方服务返回的 token；js_challenge：客户端计算的哈希值。"""


class ChallengeVerifyResponse(BaseModel):
    """挑战校验响应。"""

    success: bool
    message: str | None = None
    pass_ttl: int | None = Field(default=None, alias="passTtl")
    """通行凭据有效期（秒）。success=True 时非空，客户端可据此缓存通行状态。"""


@router.post(
    "/verify",
    response_model=SuccessResponse[ChallengeVerifyResponse],
    summary="提交挑战答案并校验",
)
async def verify_challenge(
    payload: ChallengeVerifyRequest,
    request: Request,
    resolved: ResolvedAppKey = Depends(require_app_key),
    nonce_store: NonceStore = Depends(get_nonce_store),
) -> SuccessResponse[ChallengeVerifyResponse]:
    """校验挑战答案，通过后签发通行凭据。

    1. 校验 token：签名、过期、app_id、fingerprint 一致性
    2. nonce 一次性：同一 token 只能提交一次
    3. 答案校验：captcha 调第三方 API，js_challenge 验算哈希
    4. 签发通行凭据：写 Redis `fy:challenge_pass:{site_id}:{fingerprint}` = "trusted"

    失败原因统一返回 success=False + message，不区分「token 错」「答案错」，
    避免暴露校验细节给探测方。
    
    Note:
        payload.site_id 和 resolved.site_id 实际都是站点主键（Site.id），这是
    """
    # 1. site_id 一致性：防客户端伪造调用其他租户
    if payload.site_id != resolved.site_id:
        raise AuthenticationException("API Key 与 siteId 不匹配")

    # 2. 获取 site_secret 用于验签
    resolver = get_app_key_resolver()
    secret = await resolver.get_secret_by_site_id(payload.site_id)
    if not secret:
        _logger.warning(
            "challenge_verify_no_secret",
            site_id=payload.site_id,
            fingerprint=payload.fingerprint[:8],
        )
        return SuccessResponse(
            data=ChallengeVerifyResponse(
                success=False,
                message="挑战校验失败",
            )
        )

    # 3. 校验 token：签名、过期、app_id、fingerprint 绑定
    result = verify_challenge_token(
        payload.challenge_token,
        secret=secret,
        site_id=payload.site_id,
        fingerprint=payload.fingerprint,
    )
    if not result.valid or result.payload is None:
        _logger.warning(
            "challenge_token_invalid",
            site_id=payload.site_id,
            fingerprint=payload.fingerprint[:8],
            reason=result.reason,
        )
        return SuccessResponse(
            data=ChallengeVerifyResponse(
                success=False,
                message="挑战校验失败",
            )
        )

    # 4. nonce 一次性：防重放
    if not await nonce_store.claim(payload.site_id, result.payload.nonce):
        _logger.warning(
            "challenge_token_replayed",
            site_id=payload.site_id,
            fingerprint=payload.fingerprint[:8],
            nonce=result.payload.nonce[:8],
        )
        return SuccessResponse(
            data=ChallengeVerifyResponse(
                success=False,
                message="挑战校验失败",
            )
        )

    # 5. 答案校验
    kind = result.payload.kind
    if kind == ChallengeKind.JS.value:
        # js_challenge：验证 PoW。难度取自 token 载荷——签发时定的值必须与验证时
        # 一致，从 token 读而不是读配置，避免难度调整期间在途 token 全部失效。
        if not _verify_pow(
            payload.challenge_token, payload.answer, difficulty=result.payload.difficulty
        ):
            _logger.warning(
                "challenge_pow_failed",
                site_id=payload.site_id,
                fingerprint=payload.fingerprint[:8],
            )
            return SuccessResponse(
                data=ChallengeVerifyResponse(
                    success=False,
                    message="挑战校验失败",
                )
            )
    elif kind == ChallengeKind.CAPTCHA.value:
        # captcha：TODO 接入真实第三方服务（hCaptcha / reCAPTCHA / Turnstile）
        # 当前占位：任何非空 answer 都视为通过
        if not payload.answer or len(payload.answer) < 1:
            _logger.warning(
                "challenge_answer_empty",
                site_id=payload.site_id,
                fingerprint=payload.fingerprint[:8],
            )
            return SuccessResponse(
                data=ChallengeVerifyResponse(
                    success=False,
                    message="答案不能为空",
                )
            )
    else:
        _logger.warning(
            "challenge_unknown_kind",
            site_id=payload.site_id,
            kind=kind,
        )
        return SuccessResponse(
            data=ChallengeVerifyResponse(
                success=False,
                message="挑战校验失败",
            )
        )

    # 6. 签发通行凭据
    from src.infrastructure.cache.challenge_pass_store import ChallengePassStore
    from fangyu_shared.redis_manager import get_redis

    redis = get_redis()
    pass_store = ChallengePassStore(redis)
    # 通行 TTL 取 token 过期时间与当前时间的差值，最短 60 秒
    import time

    remaining = max(result.payload.exp - int(time.time()), 60)
    await pass_store.grant(payload.site_id, payload.fingerprint, remaining)

    _logger.info(
        "challenge_passed",
        site_id=payload.site_id,
        fingerprint=payload.fingerprint[:8],
        kind=result.payload.kind,
        pass_ttl=remaining,
    )

    return SuccessResponse(
        data=ChallengeVerifyResponse(
            success=True,
            message="挑战通过",
            pass_ttl=remaining,
        )
    )


def _verify_pow(token: str, nonce_hex: str, difficulty: int) -> bool:
    """验证 Proof-of-Work：sha256(token + nonce) 的十六进制表示前 difficulty 位为 '0'。
    
    Args:
        token: challengeToken（服务端签发）
        nonce_hex: 客户端计算的 nonce（十六进制字符串）
        difficulty: 难度（前导零位数）
    
    Returns:
        True 表示验证通过
    """
    try:
        # 重算哈希
        input_str = token + nonce_hex
        hash_obj = hashlib.sha256(input_str.encode("utf-8"))
        hash_hex = hash_obj.hexdigest()
        
        # 检查前导零
        prefix = "0" * difficulty
        return hash_hex.startswith(prefix)
    except Exception as exc:
        _logger.warning("pow_verify_error", error=str(exc))
        return False
