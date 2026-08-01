"""ClickHouse 基础设施命名空间。

请显式 import 子模块使用，避免加载整个包时触发 aiochclient 等重依赖：

    from src.infrastructure.clickhouse.analytics_query import AnalyticsQueryService
"""
