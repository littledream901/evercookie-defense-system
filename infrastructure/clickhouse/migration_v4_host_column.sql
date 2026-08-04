-- =============================================================================
-- Fangyu V2 ClickHouse 增量迁移：v4 Host 列
-- -----------------------------------------------------------------------------
-- 适用场景：已有生产/测试 ClickHouse 卷，需要补充 host 列以支持访问日志域名显示。
-- 执行方式：
--   clickhouse-client --host <HOST> --database fangyu \
--                     --user <USER> --password <PASS> \
--                     --multiquery < migration_v4_host_column.sql
--
-- 幂等性：使用 ADD COLUMN IF NOT EXISTS，可安全重复执行。
-- 注意：现有表数据的 host 列会保持空串，只影响迁移后新写入的数据。
-- =============================================================================

-- 补充 host 列用于存储访问域名（从 visit_url 或 HTTP Host 头提取）
ALTER TABLE fangyu.decision_events
    ADD COLUMN IF NOT EXISTS host String DEFAULT '' AFTER user_agent;
