"""Worker 主入口：初始化依赖，启动消费者与健康服务。"""

from __future__ import annotations

import asyncio
import signal

from fangyu_shared.clickhouse_manager import ClickHouseConfig, ClickHouseManager
from fangyu_shared.logging import configure_logging, get_logger
from fangyu_shared.redis_manager import RedisConfig, RedisManager
from fangyu_shared.tracing import setup_tracing

from src.application.consumers.decision_consumer import DecisionConsumer
from src.application.transformers.event_transformer import EventTransformer
from src.application.writers.event_writer import EventWriter
from src.config import WorkerSettings, get_settings
from src.entrypoints.health_server import run_health_server
from src.infrastructure.clickhouse_batch.batch_writer import BatchWriter
from src.infrastructure.dead_letter.dead_letter import DeadLetterHandler
from src.infrastructure.stream.consumer import StreamConsumer, StreamConsumerConfig

_logger = get_logger("worker.main")


async def _bootstrap(settings: WorkerSettings) -> DecisionConsumer:
    await RedisManager.init(
        RedisConfig(
            url=settings.redis_url,
            max_connections=settings.redis_max_connections,
        )
    )
    await ClickHouseManager.init(
        ClickHouseConfig(
            url=settings.clickhouse_url,
            database=settings.clickhouse_database,
            user=settings.clickhouse_user,
            password=settings.clickhouse_password,
        )
    )

    redis = RedisManager.get_client()
    clickhouse = ClickHouseManager.get_client()

    stream_consumer = StreamConsumer(
        redis,
        StreamConsumerConfig(
            stream_name=settings.stream_name,
            group_name=settings.consumer_group,
            consumer_name=settings.consumer_name,
            batch_size=settings.stream_batch_size,
            block_ms=settings.stream_block_ms,
            claim_min_idle_ms=settings.stream_claim_min_idle_ms,
        ),
    )
    batch_writer = BatchWriter(
        clickhouse,
        table=settings.batch_target_table,
        max_retries=settings.max_retries,
        initial_backoff=settings.initial_backoff_seconds,
        max_backoff=settings.max_backoff_seconds,
    )
    dead_letter = DeadLetterHandler(
        redis,
        stream_name=settings.dead_letter_stream,
        maxlen=settings.dead_letter_maxlen,
    )
    writer = EventWriter(
        transformer=EventTransformer(),
        batch_writer=batch_writer,
        dead_letter=dead_letter,
    )
    return DecisionConsumer(stream_consumer=stream_consumer, event_writer=writer)


async def _shutdown() -> None:
    await ClickHouseManager.close()
    await RedisManager.close()


async def async_main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,  # type: ignore[arg-type]
        service_name=settings.service_name,
    )
    setup_tracing(
        service_name=settings.service_name,
        service_version=settings.version,
        otlp_endpoint=getattr(settings, "otlp_endpoint", None),
        sample_rate=getattr(settings, "trace_sample_rate", 1.0),
    )
    _logger.info("worker_starting", version=settings.version)

    consumer = await _bootstrap(settings)
    health_task = await run_health_server("0.0.0.0", settings.health_port)
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        _logger.info("worker_stopping")
        consumer.request_stop()

    try:
        loop.add_signal_handler(signal.SIGINT, _stop)
        loop.add_signal_handler(signal.SIGTERM, _stop)
    except NotImplementedError:
        # Windows fallback
        pass

    try:
        await consumer.run()
    finally:
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass
        await _shutdown()
        _logger.info("worker_stopped")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
