-- 添加 crawler_name 字段到 decision_events 表
-- 执行时间：2026-08-07
-- 说明：为访问日志爬虫识别功能添加爬虫名称字段

ALTER TABLE fangyu.decision_events
    ADD COLUMN IF NOT EXISTS crawler_name LowCardinality(String) DEFAULT '' AFTER is_bot;

-- 验证字段已添加
SELECT 
    name, 
    type, 
    default_expression
FROM system.columns
WHERE 
    database = 'fangyu' 
    AND table = 'decision_events' 
    AND name IN ('is_bot', 'crawler_name', 'crawler_category', 'crawler_vendor')
ORDER BY position;

-- 预期输出：
-- is_bot           | UInt8                       | 0
-- crawler_name     | LowCardinality(String)      | ''
-- crawler_category | LowCardinality(String)      | ''
-- crawler_vendor   | LowCardinality(String)      | ''
