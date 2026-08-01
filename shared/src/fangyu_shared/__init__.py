"""Evercookie Defense System V2 - 跨服务共享库。

包含 8 个子包：
- event_normalizer: 事件字段标准化
- exceptions: 统一异常体系与 FastAPI 处理器
- redis_manager: Redis 单例连接池
- clickhouse_manager: ClickHouse 客户端与参数化查询构建器
- logging: structlog 日志与请求上下文中间件
- metrics: Prometheus 指标注册与中间件
- schemas: 跨服务共享的 Pydantic 契约
- utils: 加密、时间、字符串、校验、异步等通用工具
"""

from __future__ import annotations

__version__ = "2.0.0"

__all__ = ["__version__"]
