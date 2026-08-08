-- API Key 表的 SQL 创建脚本
-- 如果 alembic 迁移遇到编码问题，可以直接执行此 SQL

CREATE TABLE IF NOT EXISTS sys_user_api_key (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(128) NOT NULL,
    key_prefix VARCHAR(16) NOT NULL,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    last_used_at DATETIME NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_api_key_user FOREIGN KEY (user_id) REFERENCES sys_user(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_user_api_key_user ON sys_user_api_key(user_id);
CREATE INDEX idx_user_api_key_key_hash ON sys_user_api_key(key_hash);

-- 插入迁移记录（如果使用此脚本，需要手动标记迁移已完成）
-- INSERT INTO alembic_version VALUES ('20260807_0022');
