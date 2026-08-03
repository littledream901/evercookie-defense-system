"""评分配置读取器：从 Redis 读取 admin 侧写入的站点评分开关与阈值。

键格式：``fangyu:scoring:{app_id}``（与 ScoringSync.put() 写入的 key 一致）。
无配置或 Redis 故障时回退到 GatewaySettings 里的静态默认阈值，保证 fail-safe。

本地缓存 TTL 30s，与规则仓储保持一致——评分配置属于安全策略，
管理员在后台保存后 30s 内生效，无需重启网关。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import orjson
from redis.asyncio import Redis

from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.disposition import (
    ChallengeKind,
    DecisionDisposition,
    Disposition,
    challenge,
    deny,
)

_logger = get_logger("gateway.scoring_config_cache")
_KEY_PREFIX = "fangyu:scoring"
_LOCAL_TTL = 30.0


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    """单站点运行时评分配置。

    ``enabled``
        False 时评分阶段被跳过，直接交给 DEFAULT 处置链。
    ``challenge_threshold`` / ``block_threshold``
        动态阈值，覆盖 GatewaySettings 里的静态值。
    ``disposition_suspect`` / ``disposition_hostile``
        自定义处置。None 表示沿用 pipeline 内置的 challenge(CAPTCHA) / deny()。
    ``weights``
        ``scorer 名 → 权重`` 覆盖表，已从 admin 侧的整数量纲除以 10 还原为浮点。
        空 dict 表示未配置，各 scorer 沿用类上的默认权重。
    """

    enabled: bool = True
    challenge_threshold: float = 30.0
    block_threshold: float = 75.0
    disposition_suspect: Disposition | None = None
    disposition_hostile: Disposition | None = None
    weights: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class _CacheEntry:
    config: ScoringConfig
    expires_at: float


# 站点无配置或 Redis 不可用时的兜底；由调用方用 static settings 填充默认阈值。
_FALLBACK_ENABLED = ScoringConfig()


class ScoringConfigCache:
    """按 app_id 缓存评分配置，带本地 TTL。"""

    def __init__(
        self,
        redis: Redis,
        *,
        default_challenge_threshold: float = 30.0,
        default_block_threshold: float = 75.0,
        local_ttl: float = _LOCAL_TTL,
    ) -> None:
        self._redis = redis
        self._default_challenge = default_challenge_threshold
        self._default_block = default_block_threshold
        self._local_ttl = local_ttl
        self._cache: dict[int, _CacheEntry] = {}

    async def get(self, app_id: int) -> ScoringConfig:
        """获取站点评分配置。任何错误均回退到默认值，保证不影响决策流程。"""
        now = time.monotonic()
        entry = self._cache.get(app_id)
        if entry is not None and entry.expires_at > now:
            return entry.config

        config = await self._load(app_id)
        self._cache[app_id] = _CacheEntry(config=config, expires_at=now + self._local_ttl)
        return config

    async def _load(self, app_id: int) -> ScoringConfig:
        try:
            raw = await self._redis.get(f"{_KEY_PREFIX}:{app_id}")  # type: ignore[misc]
        except Exception as exc:
            _logger.warning("scoring_config_fetch_failed", app_id=app_id, error=str(exc))
            return self._default_config()

        if not raw:
            return self._default_config()

        try:
            data = orjson.loads(raw)
        except (orjson.JSONDecodeError, TypeError):
            _logger.warning("scoring_config_parse_failed", app_id=app_id)
            return self._default_config()

        return self._parse(data)

    def _parse(self, data: dict) -> ScoringConfig:
        enabled = bool(data.get("enabled", True))
        challenge_threshold = float(
            data.get("thresholdSuspect", self._default_challenge)
        )
        block_threshold = float(
            data.get("thresholdHostile", self._default_block)
        )

        disposition_suspect = _parse_disposition(
            data.get("dispositionSuspect"), fallback=challenge(ChallengeKind.CAPTCHA)
        )
        disposition_hostile = _parse_disposition(
            data.get("dispositionHostile"), fallback=deny()
        )

        return ScoringConfig(
            enabled=enabled,
            challenge_threshold=challenge_threshold,
            block_threshold=block_threshold,
            disposition_suspect=disposition_suspect,
            disposition_hostile=disposition_hostile,
            weights=_parse_weights(data.get("weights")),
        )

    def _default_config(self) -> ScoringConfig:
        return ScoringConfig(
            enabled=True,
            challenge_threshold=self._default_challenge,
            block_threshold=self._default_block,
        )


def _parse_weights(raw: object) -> dict[str, float]:
    """把 admin 侧的整数权重表还原为 scorer 使用的浮点量纲。

    admin 存整数（-1000..1000）便于前端用滑块整数步进，scorer 类上的默认权重是
    1.0 量级，因此除以 10 —— 与 ``ScoringRule.weight`` 的既有换算保持同一比例，
    不引入第三套单位。

    非法项逐个跳过而非整表丢弃：一个维度写坏不该让其余维度也退回默认权重。
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for name, value in raw.items():
        if not isinstance(name, str):
            continue
        try:
            out[name] = float(value) / 10.0
        except (TypeError, ValueError):
            _logger.warning("scoring_weight_invalid", scorer=name, value=repr(value))
    return out


def _parse_disposition(raw: object, *, fallback: Disposition) -> Disposition:
    """把 JSON dict 解析为 Disposition；解析失败时返回兜底值。

    admin 侧存的是 ``DecisionDisposition``（无 verdict），verdict 在此按
    mechanism 推导，与规则侧走同一张映射表。这样「选了 deny 却标成 trusted」
    这类口径与行为打架的配置在数据模型层面就不存在。

    存量数据里可能残留 ``verdict`` 键（早期版本存的是完整 Disposition），
    ``DecisionDisposition`` 没有该字段，pydantic 会直接忽略，因此不需要迁移。
    """
    if not isinstance(raw, dict):
        return fallback
    try:
        return DecisionDisposition.model_validate(raw).to_disposition()
    except Exception:
        return fallback
