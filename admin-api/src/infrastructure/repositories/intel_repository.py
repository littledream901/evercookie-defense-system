"""通用情报仓储层。

支持 6 种情报类型的统一 CRUD，通过 ``IntelType`` 枚举映射到对应 ORM 模型。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from .models import (
    AsnIntelModel,
    CrawlerIntelModel,
    FingerprintIntelModel,
    GeoIpIntelModel,
    IpProfileIntelModel,
)


class IntelType(str, Enum):
    asn = "asn"
    crawler = "crawler"
    fingerprint = "fingerprint"
    geo_ip = "geo_ip"
    ip_profile = "ip_profile"


# 类型 → ORM 模型 映射
_MODEL_MAP: dict[IntelType, type[DeclarativeBase]] = {
    IntelType.asn: AsnIntelModel,
    IntelType.crawler: CrawlerIntelModel,
    IntelType.fingerprint: FingerprintIntelModel,
    IntelType.geo_ip: GeoIpIntelModel,
    IntelType.ip_profile: IpProfileIntelModel,
}

# 每种类型的唯一键字段名（用于 upsert / 查重）
_UNIQUE_KEY: dict[IntelType, str] = {
    IntelType.asn: "asn",
    IntelType.crawler: "pattern",       # feature_type + pattern 联合唯一，简化用 pattern
    IntelType.fingerprint: "finger_id",
    IntelType.geo_ip: "cidr",
    IntelType.ip_profile: "cidr",
}

# 批量插入每批行数，避免单条 SQL 过长撞 MySQL max_allowed_packet
_INSERT_CHUNK = 1000


class IntelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    def _model(self, intel_type: IntelType) -> type[DeclarativeBase]:
        return _MODEL_MAP[intel_type]

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def count(self, intel_type: IntelType, *, active_only: bool = True) -> int:
        m = self._model(intel_type)
        stmt = select(func.count()).select_from(m)
        if active_only:
            stmt = stmt.where(m.is_active.is_(True))  # type: ignore[attr-defined]
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def list_active(
        self,
        intel_type: IntelType,
        *,
        keyword: str | None = None,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Any], int]:
        m = self._model(intel_type)
        base = select(m).where(m.is_active.is_(True))  # type: ignore[attr-defined]

        if keyword:
            uk = _UNIQUE_KEY[intel_type]
            col = getattr(m, uk, None)
            if col is not None:
                base = base.where(col.contains(keyword))

        # 额外字段过滤（精确匹配，如 crawler_category）
        for field, value in (filters or {}).items():
            col = getattr(m, field, None)
            if col is not None and value is not None:
                base = base.where(col == value)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._db.execute(count_stmt)).scalar_one()

        rows_stmt = (
            base.order_by(m.id.desc())  # type: ignore[attr-defined]
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._db.execute(rows_stmt)).scalars().all()
        return list(rows), total

    async def get_by_id(self, intel_type: IntelType, row_id: int) -> Any | None:
        m = self._model(intel_type)
        return (await self._db.get(m, row_id))

    async def get_all_active(self, intel_type: IntelType) -> list[Any]:
        """用于 Redis 全量同步。"""
        m = self._model(intel_type)
        stmt = select(m).where(m.is_active.is_(True))  # type: ignore[attr-defined]
        return list((await self._db.execute(stmt)).scalars().all())

    # ── 写入 ──────────────────────────────────────────────────────────────────

    async def create(self, intel_type: IntelType, data: dict[str, Any]) -> Any:
        m = self._model(intel_type)
        row = m(**data)
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def update(self, intel_type: IntelType, row_id: int, data: dict[str, Any]) -> Any | None:
        row = await self.get_by_id(intel_type, row_id)
        if row is None:
            return None
        for k, v in data.items():
            if hasattr(row, k):
                setattr(row, k, v)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def delete(self, intel_type: IntelType, row_id: int) -> bool:
        """软删除（is_active=False）。"""
        m = self._model(intel_type)
        stmt = (
            update(m)
            .where(m.id == row_id)  # type: ignore[attr-defined]
            .values(is_active=False)
        )
        result = await self._db.execute(stmt)
        return result.rowcount > 0

    async def bulk_create(
        self, intel_type: IntelType, records: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """批量插入，重复主键跳过（INSERT IGNORE 语义）。

        返回 (imported, skipped)。
        """
        m = self._model(intel_type)
        imported = skipped = 0
        uk_field = _UNIQUE_KEY[intel_type]

        # 取唯一键集合
        existing_stmt = select(getattr(m, uk_field)).where(
            m.is_active.is_(True)  # type: ignore[attr-defined]
        )
        existing = {r[0] for r in (await self._db.execute(existing_stmt)).all()}

        pending: list[dict[str, Any]] = []
        for rec in records:
            key_val = rec.get(uk_field)
            if key_val in existing:
                skipped += 1
                continue
            pending.append(rec)
            existing.add(key_val)
            imported += 1

        # 外部源单次可达上万条，逐条 ORM add 会退化成上万次单行 INSERT，
        # 请求耗时会超过前端超时；改用多行 INSERT 分批提交。
        # executemany 要求同批各行字段一致，故先按字段集合分组（CSV 导入可能缺列）。
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for rec in pending:
            groups.setdefault(tuple(sorted(rec)), []).append(rec)

        for rows in groups.values():
            for i in range(0, len(rows), _INSERT_CHUNK):
                await self._db.execute(insert(m), rows[i : i + _INSERT_CHUNK])

        return imported, skipped

    async def count_by_note_prefix(self, intel_type: IntelType, prefixes: list[str]) -> dict[str, int]:
        """按 note 前缀分别统计活跃条目数。

        六类情报表都没有 source 列，外部源拉取的条目靠 note 里的 ``外部源:<id>``
        标记区分来源，此处据此还原各源贡献量供前端卡片展示。
        """
        m = self._model(intel_type)
        note_col = getattr(m, "note", None)
        if note_col is None:
            return {}
        out: dict[str, int] = {}
        for prefix in prefixes:
            stmt = (
                select(func.count())
                .select_from(m)
                .where(m.is_active.is_(True))  # type: ignore[attr-defined]
                .where(note_col.startswith(prefix))
            )
            out[prefix] = (await self._db.execute(stmt)).scalar_one()
        return out
