"""异步工具函数。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from typing import TypeVar

T = TypeVar("T")


async def gather_with_concurrency(
    coros: Iterable[Awaitable[T]],
    *,
    limit: int = 16,
    return_exceptions: bool = False,
) -> list[T]:
    """带并发上限的 gather。"""
    sem = asyncio.Semaphore(limit)

    async def _wrap(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro

    return await asyncio.gather(*[_wrap(c) for c in coros], return_exceptions=return_exceptions)


async def run_with_timeout(coro: Awaitable[T], timeout: float) -> T:
    """带超时的 await。"""
    return await asyncio.wait_for(coro, timeout=timeout)
