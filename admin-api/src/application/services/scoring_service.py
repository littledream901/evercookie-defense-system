"""评分配置服务。"""

from __future__ import annotations

from typing import Any

from fangyu_shared.logging import get_logger

from src.infrastructure.repositories.models import ScoringConfigModel
from src.infrastructure.repositories.scoring_repository import ScoringRepository
from src.infrastructure.scoring_sync import ScoringSync

_logger = get_logger("admin.scoring_service")

SCORING_DIMENSIONS = [
    {
        "key": "ip_reputation",
        "label": "IP 声誉",
        "description": "worker 回写的 IP 历史信誉。无信誉数据时不参与判定，不贡献基线分",
        "defaultWeight": 12,
    },
    {
        "key": "proxy",
        "label": "代理 / VPN / 数据中心",
        "description": "Tor、VPN、代理、机房 IDC 与网络类型综合判定。移动网络出口会额外降权，避免 CGNAT 误杀",
        "defaultWeight": 15,
    },
    {
        "key": "user_agent",
        "label": "UA 与爬虫特征",
        "description": "UA 结构化解析：空 UA、无法解析、爬虫类别。搜索引擎爬虫计 0 分，交由白名单处理",
        "defaultWeight": 8,
    },
    {
        "key": "device",
        "label": "设备历史",
        "description": "设备指纹的历史拦截率与信誉分。首次出现的新设备计 25 分",
        "defaultWeight": 10,
    },
    {
        "key": "behavior",
        "label": "请求异常",
        "description": "非常规 HTTP method、超长路径等请求层异常特征",
        "defaultWeight": 10,
    },
    {
        "key": "intel",
        "label": "维度情报",
        "description": "后台维护的六类维度情报。未命中情报库时不参与判定",
        "defaultWeight": 10,
    },
]
"""系统支持的评分维度，供前端渲染权重表单。

``key`` 必须与 gateway 侧 ``RiskScorer.name`` 严格一致——网关按此名查权重覆盖表，
对不上就静默沿用类默认权重，表现为「拖了滑块没效果」且无任何报错。

``defaultWeight`` 是 scorer 类上默认权重的 10 倍，与 ``weights`` 字段的整数量纲
一致（网关侧除以 10 还原）。仅用于前端展示参照值，不参与计算。
"""


class ScoringService:
    def __init__(self, repo: ScoringRepository, sync: ScoringSync) -> None:
        self._repo = repo
        self._sync = sync

    async def get(self, app_id: int) -> ScoringConfigModel | None:
        return await self._repo.get_by_app(app_id)

    async def upsert(
        self,
        app_id: int,
        *,
        name: str = "",
        enabled: bool = True,
        threshold_suspect: int = 40,
        threshold_hostile: int = 70,
        weights: dict[str, int],
        disposition_suspect: dict[str, Any] | None = None,
        disposition_hostile: dict[str, Any] | None = None,
    ) -> ScoringConfigModel:
        result = await self._repo.upsert(
            app_id,
            name=name,
            enabled=enabled,
            threshold_suspect=threshold_suspect,
            threshold_hostile=threshold_hostile,
            weights=weights,
            disposition_suspect=disposition_suspect,
            disposition_hostile=disposition_hostile,
        )
        # 同步到 Redis，gateway 通过 ScoringConfigCache 读取
        await self._sync.put(
            app_id,
            enabled=enabled,
            threshold_suspect=threshold_suspect,
            threshold_hostile=threshold_hostile,
            weights=weights,
            disposition_suspect=disposition_suspect,
            disposition_hostile=disposition_hostile,
        )
        _logger.info("scoring_config_upserted", app_id=app_id)
        return result

    async def reset(self, app_id: int) -> bool:
        deleted = await self._repo.reset(app_id)
        if deleted:
            await self._sync.delete(app_id)
            _logger.info("scoring_config_reset", app_id=app_id)
        return deleted

    @staticmethod
    def list_dimensions() -> list[dict]:
        return SCORING_DIMENSIONS
