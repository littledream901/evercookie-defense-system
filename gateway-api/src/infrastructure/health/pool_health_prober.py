"""地址池健康探测后台任务。

设计要点
--------
**熔断半开逻辑**：连续 3 次失败标记不健康，之后每 30s 放一个探测请求
（半开），成功 2 次恢复健康——避免短暂抖动导致频繁切换，也避免永久
标记不健康后无法自愈。

**探测周期**：健康地址 60s 探测一次，不健康地址 30s 尝试一次（半开）。

**并发控制**：每轮探测对所有地址并发发起，但单个地址的半开计数器与
失败计数器都是串行更新——asyncio.gather 保证同一地址不会被两个协程
同时探测（因为只有一个任务循环）。

**超时与重试**：HEAD 请求 2s 超时，不重试——探测是周期性的，下一轮
就是重试，额外重试会让探测间隔失控。

**启动时不探测**：首次探测在第一个周期结束后，避免服务启动时立即
发起大量 HEAD 请求对目标站点形成冲击。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field

import httpx

from src.infrastructure.cache.pool_health_store import PoolHealthStore

_logger = logging.getLogger(__name__)

# 探测超时 2s
_PROBE_TIMEOUT = 2.0
# 健康地址探测间隔 60s
_HEALTHY_INTERVAL = 60
# 不健康地址半开间隔 30s
_UNHEALTHY_INTERVAL = 30
# 连续失败 N 次标记不健康
_FAILURE_THRESHOLD = 3
# 半开状态下连续成功 N 次恢复健康
_RECOVERY_THRESHOLD = 2


@dataclass
class _ProbeState:
    """单个地址的探测状态（内存状态，不持久化）。"""

    consecutive_failures: int = 0
    """连续失败次数。成功一次即清零。"""
    consecutive_successes: int = 0
    """半开状态下的连续成功次数。仅在 is_healthy=False 时累加。"""
    is_healthy: bool = True
    """当前健康状态（内存缓存，定期同步到 Redis）。"""
    last_probe_time: float = 0.0
    """上次探测时间（单调时钟）。"""


class PoolHealthProber:
    """地址池健康探测器。

    单例，由 gateway-api 启动时创建并 start()，进程退出时 stop()。
    """

    def __init__(self, health_store: PoolHealthStore) -> None:
        self._store = health_store
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(_PROBE_TIMEOUT),
            follow_redirects=False,  # 不跟随重定向，探测的是配置的地址本身
        )
        self._task: asyncio.Task | None = None
        self._running = False
        # app_id -> url -> state
        self._states: dict[int, dict[str, _ProbeState]] = defaultdict(lambda: defaultdict(_ProbeState))

    async def start(self) -> None:
        """启动探测循环。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._probe_loop())
        _logger.info("PoolHealthProber started")

    async def stop(self) -> None:
        """停止探测循环。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._http.aclose()
        _logger.info("PoolHealthProber stopped")

    def register_pool(self, app_id: int, urls: list[str]) -> None:
        """注册地址池（规则发布时调用）。

        新地址初始化为健康；已存在的地址保留状态不重置——避免规则重新
        发布时把「已知不健康」的地址重置为健康导致短暂误投放。
        """
        app_states = self._states[app_id]
        for url in urls:
            if url not in app_states:
                app_states[url] = _ProbeState()

    async def _probe_loop(self) -> None:
        """探测主循环。"""
        while self._running:
            try:
                await asyncio.sleep(_HEALTHY_INTERVAL)  # 首次探测延迟一个周期
                await self._probe_all()
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                _logger.exception("probe_loop error, continue")

    async def _probe_all(self) -> None:
        """对所有已注册的地址并发探测。"""
        tasks = []
        now = asyncio.get_event_loop().time()
        for app_id, app_states in self._states.items():
            for url, state in app_states.items():
                # 根据健康状态决定探测间隔
                interval = _UNHEALTHY_INTERVAL if not state.is_healthy else _HEALTHY_INTERVAL
                if now - state.last_probe_time >= interval:
                    tasks.append(self._probe_one(app_id, url, state, now))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _probe_one(self, app_id: int, url: str, state: _ProbeState, now: float) -> None:
        """探测单个地址并更新状态。"""
        state.last_probe_time = now
        try:
            resp = await self._http.head(url)
            success = 200 <= resp.status_code < 500  # 4xx 视为成功（地址可达，只是没权限等）
        except Exception:  # noqa: BLE001 - 超时、DNS 失败、连接拒绝等都算失败
            success = False

        if success:
            state.consecutive_failures = 0
            if not state.is_healthy:
                # 半开状态下成功，累加恢复计数
                state.consecutive_successes += 1
                if state.consecutive_successes >= _RECOVERY_THRESHOLD:
                    state.is_healthy = True
                    state.consecutive_successes = 0
                    await self._store.mark_healthy(app_id, url)
                    _logger.info("pool_health recovered: app_id=%s url=%s", app_id, url)
            # 健康状态下成功，无需操作（Redis TTL 会自动过期，默认视为健康）
        else:
            state.consecutive_successes = 0
            state.consecutive_failures += 1
            if state.is_healthy and state.consecutive_failures >= _FAILURE_THRESHOLD:
                # 连续失败达阈值，标记不健康
                state.is_healthy = False
                await self._store.mark_unhealthy(app_id, url)
                _logger.warning("pool_health failed: app_id=%s url=%s failures=%s", app_id, url, state.consecutive_failures)
            elif not state.is_healthy:
                # 半开状态下失败，刷新 Redis TTL
                await self._store.mark_unhealthy(app_id, url)
