-- ============================================================
-- Stock Agent Prediction Intelligence 迁移（2026-08-30）
-- 依据《Investment Intelligence & Prediction Scoring Engine》V1.0
--   第 8 节 Prediction Intelligence（统一数据层）
--   第 18.1 节 MySQL 数据模型：prediction_source/event/market/outcome/probability/consensus/signal
-- 全部 CREATE TABLE IF NOT EXISTS，幂等可重复执行
-- ============================================================

-- 1) prediction_source：预测源配置（Polymarket P0 / Kalshi P0 / Metaculus P1 / Manifold P1）
CREATE TABLE IF NOT EXISTS prediction_source (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(32) NOT NULL COMMENT 'polymarket/kalshi/metaculus/manifold',
    name VARCHAR(64),
    source_type VARCHAR(32) DEFAULT 'api',
    base_url VARCHAR(255),
    weight DECIMAL(6,4) DEFAULT 1.0 COMMENT 'Consensus 权重（reliability/liquidity/quality）',
    reliability_score DECIMAL(6,4) DEFAULT 0.7,
    enabled TINYINT DEFAULT 1,
    priority VARCHAR(8) DEFAULT 'P1' COMMENT 'P0/P1',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) prediction_event：统一预测事件（跨源归一化后的业务事件）
CREATE TABLE IF NOT EXISTS prediction_event (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(64) COMMENT 'macro/company/industry/geopolitics/ai/crypto...',
    start_time DATETIME NULL,
    end_time DATETIME NULL COMMENT '事件到期日',
    status VARCHAR(16) DEFAULT 'open' COMMENT 'open/closed/settled',
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_category (category),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3) prediction_market：预测市场（某源上某事件的交易市场）
CREATE TABLE IF NOT EXISTS prediction_market (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED,
    source_id BIGINT UNSIGNED,
    external_id VARCHAR(128) COMMENT '源侧市场 ID（如 Kalshi ticker）',
    title VARCHAR(255),
    market_type VARCHAR(32) DEFAULT 'binary' COMMENT 'binary/multi/range',
    status VARCHAR(16) DEFAULT 'active' COMMENT 'active/closed/settled',
    yes_ask DECIMAL(10,4) NULL,
    yes_bid DECIMAL(10,4) NULL,
    last_price DECIMAL(10,4) NULL,
    volume DECIMAL(18,4) NULL,
    open_interest DECIMAL(18,4) NULL,
    liquidity DECIMAL(18,4) NULL,
    close_time DATETIME NULL,
    detail JSON,
    last_sync_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_source_external (source_id, external_id),
    KEY idx_event (event_id),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) prediction_outcome：市场结果（YES/NO 或多选结果）
CREATE TABLE IF NOT EXISTS prediction_outcome (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    market_id BIGINT UNSIGNED,
    outcome_key VARCHAR(32) COMMENT 'yes/no 或自定义',
    outcome_label VARCHAR(128),
    probability DECIMAL(8,4) COMMENT '当前概率（YES 价 0~1）',
    last_sync_at DATETIME,
    UNIQUE KEY uk_market_outcome (market_id, outcome_key),
    KEY idx_market (market_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) prediction_probability：概率历史时序（Momentum 计算基础）
CREATE TABLE IF NOT EXISTS prediction_probability (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    market_id BIGINT UNSIGNED,
    outcome_key VARCHAR(32) DEFAULT 'yes',
    probability DECIMAL(8,4),
    volume DECIMAL(18,4) NULL,
    open_interest DECIMAL(18,4) NULL,
    observed_at DATETIME,
    UNIQUE KEY uk_market_time (market_id, outcome_key, observed_at),
    KEY idx_market (market_id),
    KEY idx_time (observed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6) prediction_consensus：多源共识（Consensus = Σ(P_i×W_i)/Σ(W_i) + Dispersion）
CREATE TABLE IF NOT EXISTS prediction_consensus (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED,
    timestamp DATETIME,
    probability DECIMAL(8,4) COMMENT '加权共识概率',
    dispersion DECIMAL(8,4) COMMENT '源间离散度（标准差）',
    source_count INT,
    momentum_24h DECIMAL(8,4) COMMENT '24h 概率动量',
    momentum_7d DECIMAL(8,4) COMMENT '7d 概率动量',
    detail JSON,
    UNIQUE KEY uk_event_time (event_id, timestamp),
    KEY idx_event (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7) prediction_signal：Prediction → Stock/Industry 信号（映射后）
CREATE TABLE IF NOT EXISTS prediction_signal (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT UNSIGNED,
    entity_type VARCHAR(16) COMMENT 'stock/industry',
    entity_symbol VARCHAR(32) COMMENT '股票代码或行业代码',
    direction VARCHAR(16) COMMENT 'bullish/neutral/bearish',
    strength DECIMAL(6,4) COMMENT '信号强度 -1~1',
    confidence DECIMAL(6,4),
    probability DECIMAL(8,4) COMMENT '事件概率',
    momentum_24h DECIMAL(8,4),
    horizon VARCHAR(16) COMMENT 'short/medium/long',
    propagation_path VARCHAR(255) COMMENT '映射路径：AI CapEx→Data Center→GPU→NVDA',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_entity (entity_type, entity_symbol),
    KEY idx_event (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
