-- ============================================================
-- Stock Agent Phase5 新闻架构迁移
-- 6 张表：news_source / stock_news / stock_news_symbol
--         stock_news_analysis / stock_news_event / news_fetch_log
-- 旧 stock_news 先重命名为 stock_news_legacy，再建新表、迁移存量（不删除）
-- 注意：RENAME 必须早于 CREATE TABLE stock_news（同名冲突）
-- ============================================================

-- 1) 新闻源配置表
CREATE TABLE IF NOT EXISTS news_source (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    code VARCHAR(50) NOT NULL,
    api_type VARCHAR(30),
    base_url VARCHAR(500),
    enabled TINYINT DEFAULT 1,
    priority INT DEFAULT 100,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_source_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) 旧表改名（保留数据，便于回滚/核对）
RENAME TABLE stock_news TO stock_news_legacy;

-- 3) 原始新闻表（新闻-股票 关联移到 stock_news_symbol，支持多对多）
CREATE TABLE IF NOT EXISTS stock_news (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT UNSIGNED NOT NULL,
    source_news_id VARCHAR(255),
    title VARCHAR(1000) NOT NULL,
    summary TEXT,
    content MEDIUMTEXT,
    url VARCHAR(2000),
    image_url VARCHAR(2000),
    author VARCHAR(255),
    publisher VARCHAR(255),
    language VARCHAR(20) DEFAULT 'en',
    published_at DATETIME NOT NULL,
    fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_hash CHAR(64),
    url_hash CHAR(64),
    status VARCHAR(30) DEFAULT 'new',
    event_id BIGINT UNSIGNED NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_source_news_id (source_id, source_news_id),
    INDEX idx_published_at (published_at),
    INDEX idx_content_hash (content_hash),
    INDEX idx_url_hash (url_hash),
    INDEX idx_status (status),
    INDEX idx_event_id (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) 新闻-股票 多对多关联
CREATE TABLE IF NOT EXISTS stock_news_symbol (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    news_id BIGINT UNSIGNED NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    company_name VARCHAR(255),
    relevance_score DECIMAL(6,4),
    mention_count INT DEFAULT 1,
    is_primary TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_news_symbol (news_id, symbol),
    INDEX idx_symbol (symbol),
    INDEX idx_symbol_news (symbol, news_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) AI 分析结果（比原设计多一列 event_type，便于按事件类型检索）
CREATE TABLE IF NOT EXISTS stock_news_analysis (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    news_id BIGINT UNSIGNED NOT NULL,
    model VARCHAR(100),
    model_version VARCHAR(100),
    event_type VARCHAR(50),
    sentiment VARCHAR(20),
    sentiment_score DECIMAL(6,4),
    relevance_score DECIMAL(6,4),
    impact_score DECIMAL(6,4),
    confidence DECIMAL(6,4),
    time_horizon VARCHAR(30),
    summary TEXT,
    reasoning TEXT,
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_news_model (news_id, model, model_version),
    INDEX idx_sentiment (sentiment),
    INDEX idx_impact (impact_score),
    INDEX idx_event_type (event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6) 新闻事件聚合表
CREATE TABLE IF NOT EXISTS stock_news_event (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(1000),
    description TEXT,
    event_time DATETIME,
    impact_score DECIMAL(6,4),
    confidence DECIMAL(6,4),
    status VARCHAR(30) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_event_type (event_type),
    INDEX idx_event_time (event_time),
    INDEX idx_impact (impact_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7) 采集任务日志表
CREATE TABLE IF NOT EXISTS news_fetch_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT UNSIGNED NOT NULL,
    symbol VARCHAR(30),
    start_time DATETIME,
    end_time DATETIME,
    request_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    response_time_ms INT,
    fetched_count INT DEFAULT 0,
    inserted_count INT DEFAULT 0,
    duplicate_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    status VARCHAR(30),
    error_message TEXT,
    INDEX idx_source_time (source_id, request_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8) 初始化 Finnhub 新闻源
INSERT IGNORE INTO news_source (name, code, api_type, base_url, enabled, priority)
VALUES ('Finnhub', 'finnhub', 'finnhub', 'https://finnhub.io', 1, 10);

-- 9) 存量数据迁移：旧行以显式 id 迁入新 stock_news，symbol 拆到 stock_news_symbol
INSERT INTO stock_news (id, source_id, source_news_id, title, summary, content, url,
                        author, publisher, language, published_at, fetched_at,
                        content_hash, url_hash, status)
SELECT id, 1, CONCAT('legacy-', id), title, NULL, content, url, NULL,
       COALESCE(source, 'Finnhub'), 'en',
       COALESCE(published_at, NOW()), NOW(),
       SHA2(COALESCE(url, ''), 256), SHA2(COALESCE(title, ''), 256), 'new'
FROM stock_news_legacy;

INSERT IGNORE INTO stock_news_symbol (news_id, symbol, company_name, relevance_score, mention_count, is_primary)
SELECT id, symbol, NULL, 1.0000, 1, 1 FROM stock_news_legacy;
