-- =============================================================================
-- 迁移 v7：app_id → site_id 列名重命名（V3 双层架构重构）
-- -----------------------------------------------------------------------------
-- 背景：V3 重构将「站点维度」标识从 app_id 统一改名为 site_id，wire 层 Pydantic
--       别名从 appId → siteId。本迁移同步 ClickHouse DDL 与 ORDER BY 排序键。
--
-- 执行前提：
--   1. 必须先停止 worker 写入（否则迁移期间新数据会丢失）
--   2. 确保 Redis Stream 里的在途消息已消费完毕
--   3. 备份现有数据（可选，但强烈建议）
--
-- 执行顺序：
--   1. 删除所有物化视图（依赖旧表结构）
--   2. 对每张表：创建新表 → 数据迁移 → 重命名交换 → 保留旧表为 _backup_v2
--   3. 重建物化视图（使用新 DDL）
--   4. 恢复 worker 写入
--
-- 注意：旧表保留为 _backup_v2 后缀，不自动删除，由运维确认数据无误后手动删除。
-- =============================================================================

-- ==================== 第一步：删除物化视图 ====================
-- 物化视图依赖基表结构，必须先删除才能修改基表

DROP VIEW IF EXISTS fangyu.mv_disposition_hourly;
DROP VIEW IF EXISTS fangyu.mv_rule_hits_daily;
DROP VIEW IF EXISTS fangyu.mv_shadow_impact_daily;
DROP VIEW IF EXISTS fangyu.mv_device_hourly;
DROP VIEW IF EXISTS fangyu.mv_clock_block_hourly;
DROP VIEW IF EXISTS fangyu.mv_ip_reputation_daily;
DROP VIEW IF EXISTS fangyu.mv_fingerprint_reputation_daily;

-- ==================== 第二步：迁移 decision_events 主表 ====================
-- ORDER BY 包含 app_id，无法用 ALTER TABLE RENAME COLUMN，必须重建表

CREATE TABLE IF NOT EXISTS fangyu.decision_events_new
(
    event_id        String,
    site_id         UInt64,
    fingerprint     String,
    device_id       String DEFAULT '',
    ip              String,
    ip_type         LowCardinality(String) DEFAULT 'ipv4',
    user_agent      String DEFAULT '',
    host            String DEFAULT '',
    path            String DEFAULT '/',
    referer         String DEFAULT '',
    method          LowCardinality(String) DEFAULT 'GET',
    verdict         LowCardinality(String) DEFAULT 'trusted',
    mechanism       LowCardinality(String) DEFAULT 'pass',
    target_kind     LowCardinality(String) DEFAULT 'origin',
    target_url      String DEFAULT '',
    http_status     UInt16 DEFAULT 200,
    decided_by      LowCardinality(String) DEFAULT 'system_default',
    decided_stage   LowCardinality(String) DEFAULT 'default',
    decided_rule_id UInt64 DEFAULT 0,
    score           Float32 DEFAULT 0,
    scorer_scores   Map(LowCardinality(String), Float32),
    rule_ids        Array(UInt64) DEFAULT [],
    reason          String DEFAULT '',
    country         LowCardinality(String) DEFAULT '',
    asn             UInt32 DEFAULT 0,
    asn_org         String DEFAULT '',
    connection_type LowCardinality(String) DEFAULT 'unknown',
    is_vpn          UInt8 DEFAULT 0,
    is_proxy        UInt8 DEFAULT 0,
    device_type      LowCardinality(String) DEFAULT '',
    os_name          LowCardinality(String) DEFAULT '',
    browser_name     LowCardinality(String) DEFAULT '',
    is_bot           UInt8 DEFAULT 0,
    crawler_name     LowCardinality(String) DEFAULT '',
    crawler_category LowCardinality(String) DEFAULT '',
    crawler_vendor   LowCardinality(String) DEFAULT '',
    accept_language  String DEFAULT '',
    repeat_key         String DEFAULT '',
    repeat_value       String DEFAULT '',
    evercookie_restore UInt8 DEFAULT 0,
    shadow_rule_ids  Array(UInt64) DEFAULT [],
    shadow_verdicts  Array(LowCardinality(String)) DEFAULT [],
    ingress               LowCardinality(String) DEFAULT 'sdk',
    fingerprint_is_derived UInt8 DEFAULT 0,
    clock_counts     Map(LowCardinality(String), UInt32),
    clock_banned     UInt8 DEFAULT 0,
    behavior_event_count UInt16 DEFAULT 0,
    decision_cost_ms UInt32 DEFAULT 0,
    request_id      String DEFAULT '',
    occurred_at     DateTime64(3, 'UTC'),
    schema_version  UInt16 DEFAULT 3,
    event_version   UInt64 DEFAULT 0,
    ingested_at     DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(event_version)
PARTITION BY toYYYYMMDD(occurred_at)
ORDER BY (site_id, occurred_at, event_id)
TTL toDateTime(occurred_at) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- 迁移数据：app_id → site_id
INSERT INTO fangyu.decision_events_new
SELECT
    event_id,
    app_id AS site_id,  -- 核心：列重命名
    fingerprint,
    device_id,
    ip,
    ip_type,
    user_agent,
    host,
    path,
    referer,
    method,
    verdict,
    mechanism,
    target_kind,
    target_url,
    http_status,
    decided_by,
    decided_stage,
    decided_rule_id,
    score,
    scorer_scores,
    rule_ids,
    reason,
    country,
    asn,
    asn_org,
    connection_type,
    is_vpn,
    is_proxy,
    device_type,
    os_name,
    browser_name,
    is_bot,
    crawler_name,
    crawler_category,
    crawler_vendor,
    accept_language,
    repeat_key,
    repeat_value,
    evercookie_restore,
    shadow_rule_ids,
    shadow_verdicts,
    ingress,
    fingerprint_is_derived,
    clock_counts,
    clock_banned,
    behavior_event_count,
    decision_cost_ms,
    request_id,
    occurred_at,
    schema_version,
    event_version,
    ingested_at
FROM fangyu.decision_events;

-- 重命名交换：旧表备份，新表上位
RENAME TABLE fangyu.decision_events TO fangyu.decision_events_backup_v2;
RENAME TABLE fangyu.decision_events_new TO fangyu.decision_events;

-- 重建 bloom filter 索引
ALTER TABLE fangyu.decision_events
    ADD INDEX IF NOT EXISTS idx_ip (ip) TYPE bloom_filter(0.01) GRANULARITY 4;
ALTER TABLE fangyu.decision_events
    ADD INDEX IF NOT EXISTS idx_fingerprint (fingerprint) TYPE bloom_filter(0.01) GRANULARITY 4;
ALTER TABLE fangyu.decision_events
    ADD INDEX IF NOT EXISTS idx_request (request_id) TYPE bloom_filter(0.01) GRANULARITY 4;
ALTER TABLE fangyu.decision_events
    ADD INDEX IF NOT EXISTS idx_repeat (repeat_value) TYPE bloom_filter(0.01) GRANULARITY 4;

-- ==================== 第三步：迁移 decision_traces 表 ====================

CREATE TABLE IF NOT EXISTS fangyu.decision_traces_new
(
    request_id  String,
    site_id     UInt64,
    rule_id     UInt64 DEFAULT 0,
    rule_name   String DEFAULT '',
    field       String DEFAULT '',
    op          LowCardinality(String) DEFAULT '',
    expected    String DEFAULT '',
    actual      String DEFAULT '',
    matched     UInt8 DEFAULT 0,
    occurred_at DateTime64(3, 'UTC'),
    ingested_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(occurred_at)
ORDER BY (site_id, request_id, rule_id)
TTL toDateTime(occurred_at) + INTERVAL 7 DAY
SETTINGS index_granularity = 8192;

INSERT INTO fangyu.decision_traces_new
SELECT
    request_id,
    app_id AS site_id,  -- 核心：列重命名
    rule_id,
    rule_name,
    field,
    op,
    expected,
    actual,
    matched,
    occurred_at,
    ingested_at
FROM fangyu.decision_traces;

RENAME TABLE fangyu.decision_traces TO fangyu.decision_traces_backup_v2;
RENAME TABLE fangyu.decision_traces_new TO fangyu.decision_traces;

-- ==================== 第四步：死信表无需迁移 ====================
-- decision_events_dlq 表不包含 app_id/site_id 列，无需修改

-- ==================== 第五步：重建物化视图（新 DDL） ====================

CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_disposition_hourly
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(hour)
ORDER BY (hour, site_id, verdict, mechanism)
AS SELECT
    toStartOfHour(occurred_at) AS hour,
    site_id,
    verdict,
    mechanism,
    count() AS event_count
FROM fangyu.decision_events
GROUP BY hour, site_id, verdict, mechanism;

CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_rule_hits_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(log_date)
ORDER BY (log_date, site_id, rule_id)
AS SELECT
    toDate(occurred_at) AS log_date,
    site_id,
    arrayJoin(rule_ids) AS rule_id,
    count() AS hit_count,
    countIf(verdict = 'hostile') AS hostile_count,
    countIf(mechanism = 'challenge') AS challenge_count,
    countIf(mechanism = 'pass') AS pass_count,
    avg(score) AS avg_score
FROM fangyu.decision_events
WHERE notEmpty(rule_ids)
GROUP BY log_date, site_id, rule_id;

CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_shadow_impact_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(log_date)
ORDER BY (log_date, site_id, shadow_rule_id)
AS SELECT
    toDate(occurred_at) AS log_date,
    site_id,
    arrayJoin(shadow_rule_ids) AS shadow_rule_id,
    count() AS would_hit_count,
    countIf(mechanism = 'pass') AS currently_passed_count
FROM fangyu.decision_events
WHERE notEmpty(shadow_rule_ids)
GROUP BY log_date, site_id, shadow_rule_id;

CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_device_hourly
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(hour)
ORDER BY (hour, site_id, device_type, verdict)
AS SELECT
    toStartOfHour(occurred_at) AS hour,
    site_id,
    device_type,
    verdict,
    count() AS event_count
FROM fangyu.decision_events
GROUP BY hour, site_id, device_type, verdict;

CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_clock_block_hourly
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(hour)
ORDER BY (hour, site_id, decided_by, ingress)
AS SELECT
    toStartOfHour(occurred_at) AS hour,
    site_id,
    decided_by,
    ingress,
    count() AS block_count,
    countIf(clock_banned = 1) AS ban_count
FROM fangyu.decision_events
WHERE decided_by IN ('clock_rate_limit', 'clock_ban')
GROUP BY hour, site_id, decided_by, ingress;

CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_ip_reputation_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(log_date)
ORDER BY (log_date, site_id, ip)
AS SELECT
    toDate(occurred_at)                                              AS log_date,
    site_id,
    ip,
    count()                                                          AS total_count,
    countIf(mechanism IN ('deny', 'not_found', 'challenge'))         AS blocked_count
FROM fangyu.decision_events
WHERE ip != ''
GROUP BY log_date, site_id, ip;

CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_fingerprint_reputation_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(log_date)
ORDER BY (log_date, site_id, fingerprint)
AS SELECT
    toDate(occurred_at)                                              AS log_date,
    site_id,
    fingerprint,
    count()                                                          AS total_count,
    countIf(mechanism IN ('deny', 'not_found', 'challenge'))         AS blocked_count
FROM fangyu.decision_events
WHERE fingerprint != ''
GROUP BY log_date, site_id, fingerprint;

-- ==================== 迁移完成 ====================
-- 后续步骤：
--   1. 启动 worker，验证写入正常
--   2. 在 admin-api 上执行查询测试，确认 site_id 列可正常使用
--   3. 确认无误后，手动删除备份表：
--      DROP TABLE fangyu.decision_events_backup_v2;
--      DROP TABLE fangyu.decision_traces_backup_v2;
