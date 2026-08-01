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
    IpReputationScorer,
    ProxyScorer,
    UserAgentScorer,
)
from src.domain.risk.security import SecurityChecker
from src.domain.rule.evaluator import ConditionEvaluator
from src.domain.rule.matcher import DecisionRuleMatcher
from src.infrastructure.cache.decision_cache import DecisionCache
from src.infrastructure.cache.profile_cache import ProfileCache
from src.infrastructure.clock.repository import ClockRepository
from src.infrastructure.event_publisher.stream_publisher import StreamEventPublisher
from src.infrastructure.mmdb.reader import MMDBReader
from src.infrastructure.rule_repo.rule_repository import RuleRepository
from src.interfaces.http.middleware.app_key import AppKeyResolver

_decision_service: DecisionService | None = None
_mmdb_reader: MMDBReader | None = None
_app_key_resolver: AppKeyResolver | None = None


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
        cache_ttl=settings.app_key_cache_ttl,
        max_cache_size=settings.app_key_cache_max_size,
    )
    return _app_key_resolver


def get_app_key_resolver() -> AppKeyResolver:
    if _app_key_resolver is None:
        return build_app_key_resolver()
    return _app_key_resolver


def reset_dependencies() -> None:
    """测试或热重启时可用。"""
    global _decision_service, _mmdb_reader, _app_key_resolver
    if _mmdb_reader is not None:
        _mmdb_reader.close()
    _mmdb_reader = None
    _decision_service = None
    _app_key_resolver = None
