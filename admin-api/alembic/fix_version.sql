-- =============================================================================
-- Alembic 版本修复脚本
-- 用途：修复 "Can't locate revision identified by 'xxx'" 错误
-- 场景：数据库结构完整，但版本号与代码不匹配
-- =============================================================================

-- 1. 查看当前版本
SELECT 
    version_num AS '当前版本',
    CASE 
        WHEN version_num = '20260809_0001' THEN '✓ 版本正确'
        ELSE '✗ 版本不匹配，需要修复'
    END AS '状态'
FROM alembic_version;

-- 2. 核对数据库表结构是否完整
SELECT 
    COUNT(*) AS '总表数',
    CASE 
        WHEN COUNT(*) >= 30 THEN '✓ 表数量正常'
        ELSE '✗ 表缺失，请检查'
    END AS '状态'
FROM information_schema.tables 
WHERE table_schema = DATABASE();

-- 3. 检查关键表是否存在
SELECT 
    table_name AS '表名',
    CASE 
        WHEN table_name IS NOT NULL THEN '✓ 存在'
        ELSE '✗ 缺失'
    END AS '状态'
FROM information_schema.tables 
WHERE table_schema = DATABASE()
  AND table_name IN (
    'sys_user', 'sys_role', 'sys_user_role',
    'biz_tenant', 'biz_site',
    'rule_disposition', 'rule_site',
    'scoring_config', 'click_limit_config'
  )
ORDER BY table_name;

-- =============================================================================
-- 如果上述检查都通过，执行以下修复命令：
-- =============================================================================

-- 4. 删除旧版本号
-- DELETE FROM alembic_version;

-- 5. 插入新版本号
-- INSERT INTO alembic_version (version_num) VALUES ('20260809_0001');

-- 6. 验证修复结果
-- SELECT version_num AS '修复后版本' FROM alembic_version;

-- =============================================================================
-- 使用方法：
-- docker exec -i deploy-mysql-1 mysql -uroot -p${MYSQL_ROOT_PASSWORD} fangyu_defense < fix_version.sql
-- =============================================================================
