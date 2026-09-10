-- Skill 安全扫描历史表
-- 独立执行此脚本后，SWE/Market 服务只负责读写，不在启动时管理 DDL。

CREATE TABLE IF NOT EXISTS swe_skill_scan_history (
    id CHAR(36) NOT NULL,
    skill_name VARCHAR(255) NOT NULL,
    blocked_at DATETIME(6) NOT NULL,
    max_severity VARCHAR(16) NOT NULL,
    findings_json MEDIUMTEXT NOT NULL,
    content_hash CHAR(64) NOT NULL DEFAULT '',
    action VARCHAR(16) NOT NULL,
    source_id VARCHAR(128) NOT NULL DEFAULT '',
    user_id VARCHAR(255) NOT NULL DEFAULT '',
    bbk_id VARCHAR(128) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_swe_skill_scan_history_order (blocked_at, id),
    INDEX idx_swe_skill_scan_history_skill_action_order (
        skill_name, action, blocked_at, id
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Skill 安全扫描历史表';

DELIMITER $$

CREATE PROCEDURE migrate_swe_skill_scan_history()
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'swe_skill_scan_history'
          AND column_name = 'source_id'
    ) THEN
        ALTER TABLE swe_skill_scan_history
            ADD COLUMN source_id VARCHAR(128) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'swe_skill_scan_history'
          AND column_name = 'user_id'
    ) THEN
        ALTER TABLE swe_skill_scan_history
            ADD COLUMN user_id VARCHAR(255) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'swe_skill_scan_history'
          AND column_name = 'bbk_id'
    ) THEN
        ALTER TABLE swe_skill_scan_history
            ADD COLUMN bbk_id VARCHAR(128) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'swe_skill_scan_history'
          AND index_name = 'idx_swe_skill_scan_history_order'
    ) THEN
        CREATE INDEX idx_swe_skill_scan_history_order
            ON swe_skill_scan_history (blocked_at, id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'swe_skill_scan_history'
          AND index_name = 'idx_swe_skill_scan_history_skill_action_order'
    ) THEN
        CREATE INDEX idx_swe_skill_scan_history_skill_action_order
            ON swe_skill_scan_history (skill_name, action, blocked_at, id);
    END IF;
END$$

DELIMITER ;

CALL migrate_swe_skill_scan_history();
DROP PROCEDURE migrate_swe_skill_scan_history;
