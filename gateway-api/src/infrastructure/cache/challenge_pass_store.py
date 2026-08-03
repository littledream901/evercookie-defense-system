"""挑战通行凭据存储。

客户端完成 challenge（captcha / js_challenge）后，gateway 签发通行凭据并写入此存储：
    key = fy:challenge_pass:{app_id}:{fingerprint}
    value = "trusted"
    TTL = challenge token 的剩余有效期（通常 5 分钟）

决策流水线在 CHALLENGE_PASS 阶段查询此存储，命中即短路放行，避免重复挑战。
消费后不删除（与 nonce 不同）：同一访客在 TTL 内的多次请求都应免挑战。

与 DecisionCache 的区别：
- DecisionCache 键位包含 path / visit_url，是**请求级**缓存
- ChallengePassStore 只绑定 app_id + fingerprint，是**访客级**缓存
- 挑战通行是跨路径生效的，不能按请求维度缓存

Fail-open 策略：
- Redis 不可用时返回 None（视为未通行），交由后续流水线决策
- 不因缓存故障阻断正常流量
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError

from fangyu_shared.logging import get_logger

_KEY_PREFIX = "fy:challenge_pass"
_logger = get_logger("gateway.challenge_pass")


class ChallengePassStore:
    """挑战通行凭据查询与写入。"""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def make_key(app_id: int, fingerprint: str) -> str:
        return f"{_KEY_PREFIX}:{app_id}:{fingerprint}"

    async def check(self, app_id: int, fingerprint: str) -> bool:
        """检查访客是否持有通行凭据。

        Returns:
            True 表示持有有效通行凭据（应放行）；False 或 None 表示未通行。
        """
        if not fingerprint:
            return False
        try:
            val = await self._redis.get(self.make_key(app_id, fingerprint))
            return val == b"trusted"
        except RedisError as exc:
            _logger.warning(
                "challenge_pass_check_error",
                app_id=app_id,
                fingerprint=fingerprint[:8],
                error=str(exc),
            )
            # Fail-open：缓存故障时视为未通行，交由后续流水线
            return False

    async def grant(self, app_id: int, fingerprint: str, ttl: int) -> None:
        """签发通行凭据。

        Args:
            app_id: 应用 ID
            fingerprint: 访客指纹
            ttl: 有效期（秒），通常取 challenge token 的剩余有效期
        """
        if not fingerprint or ttl <= 0:
            return
        try:
            await self._redis.set(
                self.make_key(app_id, fingerprint),
                b"trusted",
                ex=ttl,
            )
        except RedisError as exc:
            _logger.error(
                "challenge_pass_grant_error",
                app_id=app_id,
                fingerprint=fingerprint[:8],
                ttl=ttl,
                error=str(exc),
            )
            # 静默失败：签发失败不应阻断挑战校验响应

    async def revoke(self, app_id: int, fingerprint: str) -> None:
        """撤销通行凭据（供管理接口使用）。"""
        if not fingerprint:
            return
        try:
            await self._redis.delete(self.make_key(app_id, fingerprint))
        except RedisError:
            pass
