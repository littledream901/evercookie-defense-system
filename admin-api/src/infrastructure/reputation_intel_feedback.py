"""PROF → INTEL 回流：把离线画像算出的高风险 IP 沉淀成情报条目。

为什么需要这一步
----------------
声誉分此前只写 Redis ``ProfileCache``（TTL 24 小时）。这意味着一个连续一周
被拦 95% 的 IP，只要回流任务停一天，它就退回「无声誉数据」，运营在后台也
看不到任何痕迹。把确凿的高风险结论写回情报库后：``IntelScorer`` 能消费、
条目可被检索/导出，且不随 Redis 过期而消失。

为什么写在 admin 侧而不是 worker
--------------------------------
worker 的依赖里没有 SQLAlchemy / MySQL 驱动（见 ``worker/pyproject.toml``），
只有 Redis 与 ClickHouse。为写几条情报给数据面进程引入一整套 ORM 与 DB 连接
池，代价远大于收益；admin 本就持有仓储层与 Redis 同步链路。因此周期性回流
仍由 worker 负责写 Redis，情报沉淀这一步放在 admin。

写入目标：``biz_intel_ip_profile``（``IntelType.ip_profile``）
------------------------------------------------------------
选它而不是 ``biz_threat_intel``：后者命中即在 THREAT_INTEL 阶段直接拦截，把
自动推导的结论放进去等于让离线统计拥有一票拦截权；前者作为画像补全参与
**风险打分**，由既有阈值决定最终处置，误判时的代价可控。该表以 CIDR 为唯一
键，单 IP 写成 /32（IPv6 为 /128）。
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from fangyu_shared.logging import get_logger
from fangyu_shared.reputation import IpReputationRow

from src.application.services.intel_service import IntelService
from src.infrastructure.repositories.intel_repository import IntelType

_logger = get_logger("admin.reputation_intel_feedback")

NOTE_PREFIX = "offline_profiling"
"""来源标记前缀，与外部源的 ``external:<源 id>`` 并列。

六类情报表没有 source 列，来源靠 note 前缀区分（既有约定见
``cidr_intel_fetcher.NOTE_PREFIX``）。用独立前缀让运营能一眼分清「离线画像
自动推导」与「外部源拉取 / 人工录入」，也让按来源回溯与清理成为可能。
"""

_NOTE_SOURCE = f"{NOTE_PREFIX}:reputation"


@dataclass(slots=True)
class ReputationIntelFeedbackConfig:
    """阈值与配额。全部可配，避免散落的魔法数字。"""

    enabled: bool = True
    score_threshold: float = 20.0
    """声誉分低于此值才回流。20 分 ≈ 拦截率 ≥ 80%。

    取值偏严是有意的：情报条目会影响后续所有租户对该 IP 的打分，宁可少沉淀
    也不要把共享出口（CGNAT、公司网关）写进去。
    """
    min_samples: int = 200
    """样本量下限。远高于 ProfileCache 回流的 5：写 Redis 的结论 24 小时后
    自动消失，写情报库的结论会长期留存并被所有租户消费，需要更强的证据。"""
    max_entries_per_run: int = 500
    """单次最多写入条数。

    MV 里的 IP 基数可达百万级，不设上限时一次异常流量（如压测、扫描）就能
    往情报表灌进数万行：既拖垮随后的全量 Redis 同步（gateway 侧 CIDR 匹配
    要把它们全部载入内存），也让运营无法在页面上人工复核。按分数升序取前
    N 条，保证被截断时留下的是最确凿的那些；剩下的下一轮再来。
    """


class ReputationIntelFeedback:
    """把高风险 IP 声誉写成 ip_profile 情报条目。"""

    def __init__(
        self,
        intel_service: IntelService,
        config: ReputationIntelFeedbackConfig | None = None,
    ) -> None:
        self._service = intel_service
        self._cfg = config or ReputationIntelFeedbackConfig()

    async def write(self, rows: list[IpReputationRow]) -> int:
        """筛选高风险行并批量写入，返回实际新增条数。"""
        cfg = self._cfg
        if not cfg.enabled:
            return 0

        records = self._build_records(rows)
        if not records:
            return 0

        # bulk_import 走 bulk_create 的 INSERT IGNORE 语义：已存在的 cidr 被
        # 跳过而非覆盖，因此人工修正过的条目不会被后续回流冲掉。
        result = await self._service.bulk_import(IntelType.ip_profile, records)
        imported = int(result.get("imported", 0))
        _logger.info(
            "reputation_intel_feedback_done",
            candidates=len(records),
            imported=imported,
            skipped=int(result.get("skipped", 0)),
        )
        return imported

    def _build_records(self, rows: list[IpReputationRow]) -> list[dict]:
        cfg = self._cfg

        # 同一 IP 可能在多个租户下都超阈值；情报表按 CIDR 唯一，取分数最低
        # （最恶劣）的那次观测，避免同一 cidr 在一批里重复出现。
        worst: dict[str, IpReputationRow] = {}
        for row in rows:
            if row.total < cfg.min_samples or row.score >= cfg.score_threshold:
                continue
            cidr = _to_cidr(row.ip)
            if cidr is None:
                continue
            current = worst.get(cidr)
            if current is None or row.score < current.score:
                worst[cidr] = row

        ranked = sorted(worst.items(), key=lambda kv: kv[1].score)
        if len(ranked) > cfg.max_entries_per_run:
            _logger.warning(
                "reputation_intel_feedback_truncated",
                total=len(ranked),
                cap=cfg.max_entries_per_run,
            )
            ranked = ranked[: cfg.max_entries_per_run]

        return [self._record(cidr, row) for cidr, row in ranked]

    @staticmethod
    def _record(cidr: str, row: IpReputationRow) -> dict:
        return {
            "cidr": cidr,
            # network_type 留空：本条结论来自行为统计，对「这是什么网络」
            # 一无所知。填 DATACENTER 之类的占位值会在 gateway 侧覆盖 MMDB
            # 解析出的真实网络类型（见 IntelReader._network_flags），把一个
            # 住宅 IP 说成数据中心并额外加分。空值不产生覆盖。
            "network_type": "",
            "is_vpn": False,
            "is_proxy": False,
            "is_tor": False,
            # risk_score 与 IntelScorer 的量纲一致（0-100），直接取
            # 100 - 声誉分，即观测到的拦截率百分比。
            "risk_score": round(100.0 - row.score),
            # TODO(V3 改名): row 是 shared 的 IpReputationRow，其字段名仍为 app_id
            # （对应 ClickHouse mv 的 app_id 列，实际承载站点维度）。等 ClickHouse
            # 列名与 shared dataclass 一并改名为 site_id 后，这里同步改为 row.site_id。
            "note": f"{_NOTE_SOURCE} score={row.score} samples={row.total} app={row.app_id}",
        }


def _to_cidr(ip: str) -> str | None:
    """单 IP 转成 /32（IPv6 /128）网段；非法地址返回 None。"""
    try:
        return str(ipaddress.ip_network(ip.strip(), strict=False))
    except ValueError:
        return None
