"""Application Services 命名空间。

不做 top-level re-export，避免"导入某个服务就把 ClickHouse / Redis 等
基础设施全部初始化"。业务代码请显式 import 子模块：

    from src.application.services.site_service import SiteService
"""
