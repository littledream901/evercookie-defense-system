"""FastAPI 依赖注入：构建 DecisionService 与其协作者的单例。"""

from __future__ import annotations

from functools import lru_cache

from fangyu_shared.redis_manager import get_redis

from src.application.services.decision_service import DecisionService, DecisionServiceDeps
from src.config import GatewaySettings, get_settings
from src.domain.clock.guard import ClockGuard
from src.domain.profile.builder import ProfileBuilder
from src.domain.risk.pipeline import RiskPipeline
from src.domain.risk.scorers import (
    BehaviorScorer,
    DeviceScorer,
    IntelScorer,
    InteractionScorer,
    IpReputationScorer,
    ProxyScorer,
    UserAgentScorer,
)
from src.domain.risk.security import SecurityChecker
from src.domain.rule.evaluator import ConditionEvaluator
from src.domain.rule.matcher import DecisionRuleMatcher
from src.infrastructure.cache.challenge_pass_store import ChallengePassStore
from src.infrastructure.cache.decision_cache import DecisionCache
from src.infrastructure.cache.nonce_store import NonceStore
from src.infrastructure.cache.page_resource_cache import PageResourceCache
from src.infrastructure.cache.pool_health_store import PoolHealthStore
from src.infrastructure.cache.pool_quota_store import PoolQuotaStore
from src.infrastructure.cache.profile_cache import ProfileCache
from src.infrastructure.cache.rotation_counter import RotationCounter
from src.infrastructure.cache.scoring_config_cache import ScoringConfigCache
from src.infrastructure.cache.server_session_cache import ServerSessionCache
from src.infrastructure.clock.repository import ClockRepository
from src.infrastructure.event_publisher.stream_publisher import StreamEventPublisher
from src.infrastructure.health.pool_health_prober import PoolHealthProber
from src.infrastructure.intel import IntelReader
from src.infrastructure.mmdb.reader import MMDBReader
from src.infrastructure.rule_repo.rule_repository import RuleRepository
from src.infrastructure.whitelist.reader import WhitelistReader
from src.interfaces.http.middleware.app_key import AppKeyResolver

_decision_service: DecisionService | None = None
_mmdb_reader: MMDBReader | None = None
_app_key_resolver: AppKeyResolver | None = None
_nonce_store: NonceStore | None = None
_clock_repository: ClockRepository | None = None
_health_prober: PoolHealthProber | None = None


@lru_cache(maxsize=1)
def get_gateway_settings() -> GatewaySettings:
    return get_settings()


def get_mmdb_reader() -> MMDBReader:
    global _mmdb_reader
    if _mmdb_reader is None:
        settings = get_gateway_settings()
        _mmdb_reader = MMDBReader(
            country_path=settings.mmdb_country_path,
            asn_path=settings.mmdb_asn_path,
        )
    return _mmdb_reader


def build_decision_service() -> DecisionService:
    """构建 DecisionService。放在启动阶段调用一次，缓存全局单例。"""
    global _decision_service
    if _decision_service is not None:
        return _decision_service

    settings = get_gateway_settings()
    redis = get_redis()

    scorers = [
        IpReputationScorer(),
        ProxyScorer(),
        UserAgentScorer(),
        DeviceScorer(),
        BehaviorScorer(),
        InteractionScorer(),
        IntelScorer(),
    ]

    deps = DecisionServiceDeps(
        decision_cache=DecisionCache(redis, default_ttl=settings.decision_cache_ttl),
        profile_cache=ProfileCache(redis, ttl=settings.profile_cache_ttl),
        rule_repository=RuleRepository(redis),
        profile_builder=ProfileBuilder(),
        rule_matcher=DecisionRuleMatcher(ConditionEvaluator()),
        security_checker=SecurityChecker(
            ip_blacklist=set(settings.ip_blacklist),
            country_blocklist=set(settings.country_blocklist),
            block_tor=settings.block_tor,
        ),
        risk_pipeline=RiskPipeline(
            scorers,
            challenge_threshold=settings.challenge_threshold,
            block_threshold=settings.block_threshold,
        ),
        event_publisher=StreamEventPublisher(
            redis,
            stream_name=settings.event_stream_name,
            maxlen=settings.event_stream_maxlen,
        ),
        mmdb_reader=get_mmdb_reader(),
        clock_repository=ClockRepository(redis) if settings.clock_enabled else None,
        clock_guard=ClockGuard() if settings.clock_enabled else None,
        page_resource_cache=PageResourceCache(redis),
        whitelist_reader=WhitelistReader(redis) if settings.whitelist_enabled else None,
        intel_reader=IntelReader(redis),
        scoring_config_cache=ScoringConfigCache(
            redis,
            default_challenge_threshold=settings.challenge_threshold,
            default_block_threshold=settings.block_threshold,
        ),
        server_session_cache=ServerSessionCache(redis),
        app_key_resolver=get_app_key_resolver(),
        challenge_pass_store=ChallengePassStore(redis),
        rotation_counter=RotationCounter(redis),
        pool_health_store=PoolHealthStore(redis),
        pool_quota_store=PoolQuotaStore(redis),
        health_prober=get_health_prober(),
        trace_enabled=settings.decision_trace_enabled,
        trace_sample_rate=settings.decision_trace_sample_rate,
    )
    _decision_service = DecisionService(deps)
    return _decision_service


def get_decision_service() -> DecisionService:
    if _decision_service is None:
        return build_decision_service()
    return _decision_service


def build_app_key_resolver() -> AppKeyResolver:
    """构建 API Key 解析器。启动阶段调用一次，缓存全局单例。"""
    global _app_key_resolver
    if _app_key_resolver is not None:
        return _app_key_resolver

    settings = get_gateway_settings()
    _app_key_resolver = AppKeyResolver(
        get_redis(),
        key_prefix=settings.app_key_redis_prefix,
        secret_prefix=settings.app_secret_redis_prefix,
        cache_ttl=settings.app_key_cache_ttl,
        max_cache_size=settings.app_key_cache_max_size,
    )
    return _app_key_resolver


def get_app_key_resolver() -> AppKeyResolver:
    if _app_key_resolver is None:
        return build_app_key_resolver()
    return _app_key_resolver


def build_health_prober() -> PoolHealthProber:
    """构建健康探测器。启动阶段调用一次，缓存全局单例。"""
    global _health_prober  # noqa: PLW0603
    if _health_prober is not None:
        return _health_prober
    redis = get_redis()
    health_store = PoolHealthStore(redis)
    _health_prober = PoolHealthProber(health_store)
    return _health_prober


def get_health_prober() -> PoolHealthProber:
    """获取健康探测器（供 DecisionService 注册地址池用）。"""
    if _health_prober is None:
        return build_health_prober()
    return _health_prober


def get_nonce_store() -> NonceStore:
    """Nonce 存储：与签名时间窗共用同一 TTL。"""
    global _nonce_store
    if _nonce_store is None:
        settings = get_gateway_settings()
        _nonce_store = NonceStore(get_redis(), ttl=settings.signature_window)
    return _nonce_store


def get_clock_repository() -> ClockRepository | None:
    """Clock 仓储。``clock_enabled=False`` 时返回 None，行为上报将被静默丢弃。"""
    global _clock_repository
    if not get_gateway_settings().clock_enabled:
        return None
    if _clock_repository is None:
        _clock_repository = ClockRepository(get_redis())
    return _clock_repository


def reset_dependencies() -> None:
    """重置所有全局依赖（测试与关闭时调用）。"""
    global _decision_service, _mmdb_reader, _app_key_resolver, _nonce_store
    global _clock_repository, _health_prober
    if _mmdb_reader is not None:
        _mmdb_reader.close()
    _mmdb_reader = None
    _decision_service = None
    _app_key_resolver = None
    _nonce_store = None
    _clock_repository = None
    _health_prober = None
