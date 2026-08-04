"""Gateway 侧威胁情报 Redis 查询器。

只做读操作，零数据库连接，纯 Redis SISMEMBER O(1)。

为什么一次 pipeline 而不是逐类 SISMEMBER
----------------------------------------
命中总集后还要判定归属哪几类。逐个 ``sismember`` 是 1 + 6 = 7 次往返，
且这 7 次都串在决策热路径上——单次 RTT 1ms 的内网就是 7ms，跨可用区更糟。
所有查询彼此无依赖，合成一次 pipeline 后固定为 1 次往返。

代价是即使总集未命中也把 6 个分类查询一起发出去（多传输 6 条命令、
多算 6 次 O(1) SISMEMBER）。这点服务端开销远小于省掉的 6 次 RTT。
"""

from __future__ import annotations

from dataclasses import dataclass

from fangyu_shared.logging import get_logger
from fangyu_shared.redis_manager import RedisManager

_logger = get_logger("gateway.threat_intel")

_PREFIX = "fangyu:threat_intel"
_ALL_KEY = f"{_PREFIX}:all"


@dataclass(frozen=True, slots=True)
class ThreatIntelResult:
    is_threat: bool
    categories: list[str]


_CLEAN = ThreatIntelResult(is_threat=False, categories=[])


class ThreatIntelReader:
    """从 Redis 查询 IP 是否在威胁情报库中。"""

    _KNOWN_CATEGORIES = ["malicious", "proxy", "vpn", "tor", "datacenter", "bot"]

    @classmethod
    def _key(cls, category: str) -> str:
        return f"{_PREFIX}:{category}"

    @classmethod
    async def check(cls, ip: str) -> ThreatIntelResult:
        """判断 IP 是否命中威胁情报，并给出命中的分类。

        Redis 故障按**未命中**处理（fail-open）。这个方向是刻意选的：情报阶段
        排在规则与安全检查之间，若按「命中」处理，Redis 一挂就是全站 deny——
        用一个富化信号的可用性换掉整站可用性。fail-open 的代价只是情报库里的
        坏 IP 在故障窗口内退回评分与安全检查判定，它们本来也是拦截链的一环。

        这也与白名单的 fail-closed 取向自洽：两者都收敛到「Redis 故障时不改变
        既有拦截强度，只是少了一层增益」。
        """
        # 连 get_client() 一起裹进 try：管理器未初始化时它自己就会抛，
        # 而那同样不该表现为决策 500。
        try:
            redis = RedisManager.get_client()
            # 一次 pipeline 取回总集 + 6 个分类。transaction=False：这些是纯读命令，
            # 不需要 MULTI 的原子性，省掉一次 EXEC 往返。
            pipe = redis.pipeline(transaction=False)
            pipe.sismember(_ALL_KEY, ip)
            for cat in cls._KNOWN_CATEGORIES:
                pipe.sismember(cls._key(cat), ip)
            results = await pipe.execute()
        # 捕获全部异常而非仅 RedisError：连接池耗尽等故障会被包装成别的类型，
        # 收窄后仍会把决策请求变成 500。
        except Exception as exc:
            _logger.warning("threat_intel_lookup_failed", ip=ip, error=str(exc))
            return _CLEAN

        if not results or not results[0]:
            return _CLEAN
        matched = [
            cat
            for cat, hit in zip(cls._KNOWN_CATEGORIES, results[1:], strict=False)
            if hit
        ]
        return ThreatIntelResult(is_threat=True, categories=matched)
