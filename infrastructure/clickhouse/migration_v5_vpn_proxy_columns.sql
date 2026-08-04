-- =============================================================================
-- ClickHouse Schema Migration v5: 添加 VPN/Proxy 检测字段
-- -----------------------------------------------------------------------------
-- 变更内容：
--   decision_events 表新增 is_vpn / is_proxy 两列，用于存储 IP 画像的
--   VPN/Proxy 检测结果（由 MMDB ASN org 名称启发式推断）。
--
-- 执行前提：
--   - 已应用 v4 (host column)
--   - Gateway / Worker 已更新到支持这两个字段的版本
--
-- 回滚：
--   ALTER TABLE fangyu.decision_events DROP COLUMN is_vpn;
--   ALTER TABLE fangyu.decision_events DROP COLUMN is_proxy;
-- =============================================================================

ALTER TABLE fangyu.decision_events
    ADD COLUMN IF NOT EXISTS is_vpn UInt8 DEFAULT 0
    AFTER connection_type;

ALTER TABLE fangyu.decision_events
    ADD COLUMN IF NOT EXISTS is_proxy UInt8 DEFAULT 0
    AFTER is_vpn;
