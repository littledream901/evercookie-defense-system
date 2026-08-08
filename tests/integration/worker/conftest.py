"""worker 集成测试专用 fixture。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncIterator

import pytest_asyncio

_ROOT = Path(__file__).resolve().parents[3]
_WORKER = _ROOT / "worker"

for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_name, None)

_other = {str(_WORKER.parent / n) for n in ("admin-api", "gateway-api")}
sys.path[:] = [p for p in sys.path if p not in _other]
if str(_WORKER) not in sys.path:
    sys.path.insert(0, str(_WORKER))


@pytest_asyncio.fixture(scope="function")
async def worker_runtime(integration_env: dict) -> AsyncIterator[dict]:
    from fangyu_shared.clickhouse_manager import ClickHouseConfig, ClickHouseManager
    from fangyu_shared.redis_manager import RedisConfig, RedisManager

    from src.application.transformers.event_transformer import EventTransformer
    from src.application.writers.event_writer import EventWriter
    from src.infrastructure.clickhouse_batch.batch_writer import BatchWriter
    from src.infrastructure.dead_letter.dead_letter import DeadLetterHandler

    await RedisManager.init(RedisConfig(url=integration_env["WORKER_REDIS_URL"], max_connections=20))
    await ClickHouseManager.init(
        ClickHouseConfig(
            url=integration_env["WORKER_CLICKHOUSE_URL"],
            database="fangyu",
            user="default",
            password="",
        )
    )

    try:
        redis = RedisManager.get_client()
        clickhouse = ClickHouseManager.get_client()
        await clickhouse.execute("CREATE DATABASE IF NOT EXISTS fangyu")
        await clickhouse.execute(
            """
            CREATE TABLE IF NOT EXISTS fangyu.decision_events
            (
                event_id String,
                site_id UInt64,
                fingerprint String,
                device_id String DEFAULT '',
                ip String,
                ip_type String DEFAULT 'ipv4',
                user_agent String DEFAULT '',
                path String DEFAULT '/',
                action String DEFAULT 'allow',
                disposition String DEFAULT 'ALLOW',
                dispatch_type String DEFAULT 'unknown',
                score Float32 DEFAULT 0,
                rule_ids Array(UInt64) DEFAULT [],
                reason String DEFAULT '',
                request_id String DEFAULT '',
                occurred_at DateTime64(3, 'UTC'),
                schema_version UInt16 DEFAULT 1,
                event_version UInt64 DEFAULT 0,
                ingested_at DateTime DEFAULT now()
            )
            ENGINE = ReplacingMergeTree(event_version)
            PARTITION BY toYYYYMMDD(occurred_at)
            ORDER BY (event_id, site_id, occurred_at)
            """
        )
        await clickhouse.execute("TRUNCATE TABLE fangyu.decision_events")

        yield {
            "redis": redis,
            "clickhouse": clickhouse,
            "writer": EventWriter(
                transformer=EventTransformer(),
                batch_writer=BatchWriter(clickhouse, table="fangyu.decision_events"),
                dead_letter=DeadLetterHandler(redis),
            ),
        }
    finally:
        await ClickHouseManager.close()
        await RedisManager.close()
