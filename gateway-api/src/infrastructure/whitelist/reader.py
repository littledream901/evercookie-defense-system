"""白名单查询：一次 HMGET 判定 IP 与指纹两条轴。

走实例注入（构造时传 Redis）而非 ``ThreatIntelReader`` 那种类方法 +
``RedisManager.get_client()`` 的静态写法。静态写法在测试里只能靠 patch 全局
管理器替身，而白名单要在**每个请求最前面**执行，需要能直接注入 fake 断言
调用次数。
"""

from __future__ import annotations

from dataclasses import dataclass

import orjson
from fangyu_shared.logging import get_logger
from fangyu_shared.whitelist.keys import (
    WhitelistDimension,
    field_name,
    whitelist_key,
)
from redis.asyncio import Redis

_logger = get_logger("gateway.whitelist")


@dataclass(frozen=True, slots=True)
class WhitelistHit:
    """白名单命中结果。"""

    matched: bool
    dimension: WhitelistDimension | None = None
    value: str | None = None
    note: str = ""

    @property
    def reason(self) -> str:
        """落库与响应里的原因字段。

        带上维度与值，便于排查「这个请求为什么没被拦」——白名单命中在日志里
        表现为一个凭空放行的请求，没有值就无从追溯是哪条配置生效了。
        """
        if not self.matched or self.dimension is None:
            return "whitelist"
        return f"whitelist:{self.dimension.value}:{self.value}"


_MISS = WhitelistHit(matched=False)


class WhitelistReader:
    """从 Redis Hash 查询 app 级白名单。"""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def check(
        self, app_id: int, *, ip: str, fingerprint: str
    ) -> WhitelistHit:
        """判断 IP 或指纹是否在白名单中。

        IP 优先于指纹：IP 是运维最常用的维度（放行办公网、监控探针），命中时
        原因里给出 IP 比给出一串指纹更有排查价值。

        Redis 故障按**未命中**处理（fail-closed）。这与 nonce 的 fail-open
        取向相反，理由是方向不同：nonce 失败放宽的是重放保护，而白名单失败
        若按「命中」处理，等于 Redis 一挂全站风控停摆。fail-closed 的代价只是
        白名单访客退回正常风控流程——他们本就该能通过绝大多数检查。
        """
        ip_field = field_name(WhitelistDimension.IP, ip)
        fp_field = field_name(WhitelistDimension.FINGERPRINT, fingerprint)
        try:
            values = await self._redis.hmget(  # type: ignore[misc]
                whitelist_key(app_id), [ip_field, fp_field]
            )
        # 捕获全部异常：白名单在流水线最前面，任何 Redis 故障都不该把决策
        # 请求变成 500。收窄成 RedisError 会漏掉连接池耗尽等包装过的异常。
        except Exception as exc:
            _logger.warning("whitelist_lookup_failed", app_id=app_id, error=str(exc))
            return _MISS

        if not values:
            return _MISS

        ip_raw = values[0] if len(values) > 0 else None
        fp_raw = values[1] if len(values) > 1 else None

        if ip_raw is not None:
            return WhitelistHit(
                matched=True,
                dimension=WhitelistDimension.IP,
                value=ip,
                note=_note_of(ip_raw),
            )
        if fp_raw is not None:
            return WhitelistHit(
                matched=True,
                dimension=WhitelistDimension.FINGERPRINT,
                value=fingerprint,
                note=_note_of(fp_raw),
            )
        return _MISS


def _note_of(raw: object) -> str:
    """从 field value 里取备注。

    解析失败返回空串而不抛：白名单**已经命中**了，元信息坏掉不该把放行变成
    500。value 曾经被写成空串或非 JSON 的情况在手工 ``HSET`` 调试后很常见。
    """
    if not raw:
        return ""
    try:
        meta = orjson.loads(raw)
    except (orjson.JSONDecodeError, TypeError, ValueError):
        return ""
    if not isinstance(meta, dict):
        return ""
    note = meta.get("note", "")
    return note if isinstance(note, str) else ""
