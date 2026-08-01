-- =============================================================================
-- Fangyu V2 ClickHouse 增量迁移：v3 Clock 列
-- -----------------------------------------------------------------------------
-- 适用场景：已有生产/测试 ClickHouse 卷，init.sql 只在空卷时执行，无法补列。
-- 执行方式：
--   clickhouse-client --host <HOST> --database fangyu \
--                     --user <USER> --password <PASS> \
--                     --multiquery < migration_v3_clock_columns.sql
--
-- 幂等性：所有 ADD COLUMN 使用 IF NOT EXISTS，可安全重复执行。
-- 注意：物化视图 DROP + RECREATE 期间源表写入不中断，但视图不会落数据；
--        建议在低峰期执行，或在下面的 RECREATE 前先暂停 worker。
-- =============================================================================

-- ---------- 1. 补新列 ----------
ALTER TABLE fangyu.decision_events
    ADD COLUMN IF NOT EXISTS ingress LowCardinality(String) DEFAULT 'sdk',
    ADD COLUMN IF NOT EXISTS fingerprint_is_derived UInt8 DEFAULT 0,
    ADD COLUMN IF NOT EXISTS clock_counts Map(LowCardinality(String), UInt32),
    ADD COLUMN IF NOT EXISTS clock_banned UInt8 DEFAULT 0,
    ADD COLUMN IF NOT EXISTS behavior_event_count UInt16 DEFAULT 0;

-- ---------- 2. 重建依赖新列的物化视图 ----------
-- mv_clock_block_hourly 引用 ingress 和 clock_banned，必须在补列后重建。
-- 其他视图（mv_disposition_hourly / mv_rule_hits_daily 等）不引用新列，无需改动。

DROP TABLE IF EXISTS fangyu.mv_clock_block_hourly;

CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_clock_block_hourly
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(hour)
ORDER BY (hour, app_id, decided_by, ingress)
AS SELECT
    toStartOfHour(occurred_at) AS hour,
    app_id,
    decided_by,
    ingress,
    count() AS block_count,
    countIf(clock_banned = 1) AS ban_count
FROM fangyu.decision_events
WHERE decided_by IN ('clock_rate_limit', 'clock_ban')
GROUP BY hour, app_id, decided_by, ingress;
