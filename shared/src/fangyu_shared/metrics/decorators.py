"""通用指标装饰器。"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from prometheus_client import Counter, Histogram

F = TypeVar("F", bound=Callable[..., Any])


def track_latency(
    histogram: Histogram,
    *,
    labels: dict[str, str] | None = None,
) -> Callable[[F], F]:
    """记录函数耗时（秒）到指定的 Histogram。"""
    label_values = labels or {}

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    _observe(histogram, label_values, time.perf_counter() - start)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                _observe(histogram, label_values, time.perf_counter() - start)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def track_errors(
    counter: Counter,
    *,
    labels: dict[str, str] | None = None,
    reraise: bool = True,
) -> Callable[[F], F]:
    """统计函数抛出的异常次数，默认继续抛出。"""
    label_values = labels or {}

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await func(*args, **kwargs)
                except Exception:
                    _inc(counter, label_values)
                    if reraise:
                        raise
                    return None

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception:
                _inc(counter, label_values)
                if reraise:
                    raise
                return None

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _observe(histogram: Histogram, labels: dict[str, str], value: float) -> None:
    if labels:
        histogram.labels(**labels).observe(value)
    else:
        histogram.observe(value)


def _inc(counter: Counter, labels: dict[str, str]) -> None:
    if labels:
        counter.labels(**labels).inc()
    else:
        counter.inc()


__all__ = ["track_errors", "track_latency"]

# 保留一个异步兼容占位符，方便测试 mypy 严格模式
_ASYNC: Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]] | None = None
