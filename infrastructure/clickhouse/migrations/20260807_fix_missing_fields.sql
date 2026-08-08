-- 修复缺失的 asn_org 和 is_bot 字段
-- 执行时间：2026-08-07
-- 说明：补充之前迁移遗漏的字段

-- 添加 asn_org 字段（ASN组织名称）
ALTER TABLE fangyu.decision_events
    ADD COLUMN IF NOT EXISTS asn_org String DEFAULT '' AFTER asn;

-- 添加 is_bot 字段（是否为机器人）
ALTER TABLE fangyu.decision_events
    ADD COLUMN IF NOT EXISTS is_bot UInt8 DEFAULT 0 AFTER browser_name;

-- 验证字段已添加
SELECT 
    name, 
    type, 
    default_expression
FROM system.columns
WHERE 
    database = 'fangyu' 
    AND table = 'decision_events' 
    AND name IN ('asn', 'asn_org', 'connection_type', 'browser_name', 'is_bot', 'crawler_name')
ORDER BY position;
