-- =============================================================================
-- Fangyu V2 ClickHouse Schema
-- -----------------------------------------------------------------------------
-- 表拆分策略（按访问模式与生命周期）
--   decision_events        热，90 天，全量。只放标量，供过滤与聚合。
--   decision_traces        冷，7 天，采样。规则条件命中明细，按 request_id 点查。
--
-- 关键设计
--   1. 存解析结果而非原料：country/asn/device_type/os_name 等直接落库。
--      user_agent 原文无法在 SQL 里做正则，只留作排障参考。
--   2. scorer_scores 用 Map 而非 JSON String，可直接过滤聚合：
--        WHERE scorer_scores['proxy'] > 20
--   3. ORDER BY 以 app_id 前置，匹配多租户查询模式；event_id 留在末位仍满足
--      ReplacingMergeTree 去重（去重作用于完整排序键）。
--   4. 枚举列统一 LowCardinality，显著降低存储与扫描成本。
-- =============================================================================

CREATE DATABASE IF NOT EXISTS fangyu;

-- ==================== 决策事件主表 ====================
CREATE TABLE IF NOT EXISTS fangyu.decision_events
(
    event_id        String,
    app_id          UInt64,
    fingerprint     String,
    device_id       String DEFAULT '',
    ip              String,
    ip_type         LowCardinality(String) DEFAULT 'ipv4',
    user_agent      String DEFAULT '',
    host            String DEFAULT '',
    path            String DEFAULT '/',
    referer         String DEFAULT '',
    method          LowCardinality(String) DEFAULT 'GET',

    -- 处置三层：裁决 / 机制 / 目标
    verdict         LowCardinality(String) DEFAULT 'trusted',
    mechanism       LowCardinality(String) DEFAULT 'pass',
    target_kind     LowCardinality(String) DEFAULT 'origin',
    target_url      String DEFAULT '',
    http_status     UInt16 DEFAULT 200,

    -- 处置溯源：回答「这个请求为什么被这样处置」
    decided_by      LowCardinality(String) DEFAULT 'system_default',
    decided_stage   LowCardinality(String) DEFAULT 'default',
    decided_rule_id UInt64 DEFAULT 0,

    -- 评分
    score           Float32 DEFAULT 0,
    scorer_scores   Map(LowCardinality(String), Float32),
    rule_ids        Array(UInt64) DEFAULT [],
    reason          String DEFAULT '',

    -- 网络解析结果（MMDB 产物）
    country         LowCardinality(String) DEFAULT '',
    asn             UInt32 DEFAULT 0,
    connection_type LowCardinality(String) DEFAULT 'unknown',
    is_vpn          UInt8 DEFAULT 0,
    is_proxy        UInt8 DEFAULT 0,

    -- 设备解析结果（UA parser 产物）
    device_type      LowCardinality(String) DEFAULT '',
    os_name          LowCardinality(String) DEFAULT '',
    browser_name     LowCardinality(String) DEFAULT '',
    is_bot           UInt8 DEFAULT 0,
    crawler_category LowCardinality(String) DEFAULT '',
    crawler_vendor   LowCardinality(String) DEFAULT '',

    -- 客户端语言偏好
    accept_language  String DEFAULT '',

    -- 访客追踪（Evercookie 自愈）
    repeat_key         String DEFAULT '',
    repeat_value       String DEFAULT '',
    evercookie_restore UInt8 DEFAULT 0,

    -- 影子评估：草稿规则命中但不影响结果，用于发布前测算影响面
    shadow_rule_ids  Array(UInt64) DEFAULT [],
    shadow_verdicts  Array(LowCardinality(String)) DEFAULT [],

    -- 接入来源：sdk 有真指纹与行为时序，adapter 只有服务端字段。
    -- 两条路径的信号丰富度差异很大，聚合时必须分开看，否则 adapter 流量的
    -- 派生指纹会污染「独立设备数」这类指标。
    ingress               LowCardinality(String) DEFAULT 'sdk',
    fingerprint_is_derived UInt8 DEFAULT 0,

    -- Clock 频控计数。用 Map 是为了能直接回答「阈值设多少合适」：
    --   SELECT quantile(0.99)(clock_counts['ip_short']) FROM decision_events
    -- 没有这份数据，频控阈值只能靠猜。
    clock_counts     Map(LowCardinality(String), UInt32),
    clock_banned     UInt8 DEFAULT 0,
    behavior_event_count UInt16 DEFAULT 0,

    -- 性能
    decision_cost_ms UInt32 DEFAULT 0,

    request_id      String DEFAULT '',
    occurred_at     DateTime64(3, 'UTC'),
    schema_version  UInt16 DEFAULT 3,
    event_version   UInt64 DEFAULT 0,
    ingested_at     DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(event_version)
PARTITION BY toYYYYMMDD(occurred_at)
ORDER BY (app_id, occurred_at, event_id)
TTL toDateTime(occurred_at) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- IP / fingerprint 高基维查询用 bloom filter 加速
ALTER TABLE fangyu.decision_events
    ADD INDEX IF NOT EXISTS idx_ip (ip) TYPE bloom_filter(0.01) GRANULARITY 4;
ALTER TABLE fangyu.decision_events
    ADD INDEX IF NOT EXISTS idx_fingerprint (fingerprint) TYPE bloom_filter(0.01) GRANULARITY 4;
-- 排障按 request_id 点查
ALTER TABLE fangyu.decision_events
    ADD INDEX IF NOT EXISTS idx_request (request_id) TYPE bloom_filter(0.01) GRANULARITY 4;
-- 访客追踪按 repeat_value 反查
ALTER TABLE fangyu.decision_events
    ADD INDEX IF NOT EXISTS idx_repeat (repeat_value) TYPE bloom_filter(0.01) GRANULARITY 4;

-- ==================== 规则条件命中明细（冷表） ====================
-- 体量大、查询频率极低（仅排障时按 request_id 点查），因此独立成表：
--   - TTL 7 天（主表 90 天）
--   - 写入侧只写非 trusted 裁决 + trusted 抽样，避免为 99% 正常流量存明细
CREATE TABLE IF NOT EXISTS fangyu.decision_traces
(
    request_id  String,
    app_id      UInt64,
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
ORDER BY (app_id, request_id, rule_id)
TTL toDateTime(occurred_at) + INTERVAL 7 DAY
SETTINGS index_granularity = 8192;

-- ==================== 死信事件表 ====================
-- 与 Redis Stream 的 DLQ 并存：DLQ 用于短期回捞，本表用于长期审计
CREATE TABLE IF NOT EXISTS fangyu.decision_events_dlq
(
    message_id      String,
    reason          String,
    payload         String,
    dead_at         DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(dead_at)
ORDER BY (dead_at, message_id)
TTL dead_at + INTERVAL 30 DAY;

-- ==================== 物化视图：每小时处置分布 ====================
CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_disposition_hourly
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(hour)
ORDER BY (hour, app_id, verdict, mechanism)
AS SELECT
    toStartOfHour(occurred_at) AS hour,
    app_id,
    verdict,
    mechanism,
    count() AS event_count
FROM fangyu.decision_events
GROUP BY hour, app_id, verdict, mechanism;

-- ==================== 物化视图：规则命中统计 ====================
CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_rule_hits_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(log_date)
ORDER BY (log_date, app_id, rule_id)
AS SELECT
    toDate(occurred_at) AS log_date,
    app_id,
    arrayJoin(rule_ids) AS rule_id,
    count() AS hit_count,
    countIf(verdict = 'hostile') AS hostile_count,
    countIf(mechanism = 'challenge') AS challenge_count,
    countIf(mechanism = 'pass') AS pass_count,
    avg(score) AS avg_score
FROM fangyu.decision_events
WHERE notEmpty(rule_ids)
GROUP BY log_date, app_id, rule_id;

-- ==================== 物化视图：影子规则影响面 ====================
-- 支撑「这条草稿规则发布后会多拦多少流量」的发布前评估
CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_shadow_impact_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(log_date)
ORDER BY (log_date, app_id, shadow_rule_id)
AS SELECT
    toDate(occurred_at) AS log_date,
    app_id,
    arrayJoin(shadow_rule_ids) AS shadow_rule_id,
    count() AS would_hit_count,
    countIf(mechanism = 'pass') AS currently_passed_count
FROM fangyu.decision_events
WHERE notEmpty(shadow_rule_ids)
GROUP BY log_date, app_id, shadow_rule_id;

-- ==================== 物化视图：设备维度分布 ====================
-- 依赖落库的 UA 解析结果；旧版只存 user_agent 原文，此类聚合无法实现
CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_device_hourly
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(hour)
ORDER BY (hour, app_id, device_type, verdict)
AS SELECT
    toStartOfHour(occurred_at) AS hour,
    app_id,
    device_type,
    verdict,
    count() AS event_count
FROM fangyu.decision_events
GROUP BY hour, app_id, device_type, verdict;

-- ==================== 物化视图：频控拦截小时分布 ====================
-- 频控是最容易造成大面积误伤的手段，必须能按小时看到拦截量的突变。
-- 只统计 Clock 阶段产生的拦截，与规则拦截分开——两者的调优手段完全不同。
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

-- ==================== 物化视图：IP 声誉（每日） ====================
-- 为 IpReputationScorer 提供数据源；reputation_writer / admin /sync 读此 MV。
-- SummingMergeTree 累加字段跨分区重复，查询时必须 GROUP BY + sum()。
-- 现有 mv_device_hourly 按 device_type 聚合，喂不了单 IP reputation，
-- 故此 MV 补全该缺失。
CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_ip_reputation_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(log_date)
ORDER BY (log_date, app_id, ip)
AS SELECT
    toDate(occurred_at)                                              AS log_date,
    app_id,
    ip,
    count()                                                          AS total_count,
    countIf(mechanism IN ('deny', 'not_found', 'challenge'))         AS blocked_count
FROM fangyu.decision_events
WHERE ip != ''
GROUP BY log_date, app_id, ip;

-- ==================== 物化视图：设备指纹声誉（每日） ====================
-- 现有 mv_device_hourly 按 device_type 聚合，不含单个 fingerprint，
-- 无法喂单设备 reputation；此 MV 补全这一缺失。
CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.mv_fingerprint_reputation_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(log_date)
ORDER BY (log_date, app_id, fingerprint)
AS SELECT
    toDate(occurred_at)                                              AS log_date,
    app_id,
    fingerprint,
    count()                                                          AS total_count,
    countIf(mechanism IN ('deny', 'not_found', 'challenge'))         AS blocked_count
FROM fangyu.decision_events
WHERE fingerprint != ''
GROUP BY log_date, app_id, fingerprint;
