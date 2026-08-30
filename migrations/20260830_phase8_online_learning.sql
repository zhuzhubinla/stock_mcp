-- ============================================================
-- Stock Agent Phase 8：Online Learning / Continuous Calibration 迁移（2026-08-30）
-- 依据《Investment Intelligence & Prediction Scoring Engine》V1.0
--   第 7 节 Precondition/Context Engine
--   第 13-14 节 Dynamic Scoring + Overall Score
--   第 18-19 节 MySQL 数据模型（stock_precondition/stock_context/score_snapshot/score_component/score_weight_config/signal_conflict）
--   第 26 节 Phase 8 Online Learning / Continuous Calibration
-- 全部 CREATE TABLE IF NOT EXISTS，幂等可重复执行
-- ============================================================

-- 1) market_regime：市场状态快照（Market Precondition 的市场层输入）
CREATE TABLE IF NOT EXISTS market_regime (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    regime VARCHAR(32) COMMENT 'risk_on / risk_off / neutral',
    regime_score DECIMAL(6,4) COMMENT '0~1，1=强风险偏好',
    trend_score DECIMAL(6,4) COMMENT '指数趋势分 0~1',
    volatility_score DECIMAL(6,4) COMMENT '波动分 0~1（越高=越平稳）',
    breadth_score DECIMAL(6,4) COMMENT '市场宽度 0~1',
    macro_score DECIMAL(6,4) COMMENT '宏观状态分 0~1',
    detail JSON,
    snapshot_time DATETIME,
    KEY idx_time (snapshot_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) stock_precondition：每股 Context Vector（Precondition Engine 输出）
CREATE TABLE IF NOT EXISTS stock_precondition (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    stock_id BIGINT UNSIGNED,
    valuation DECIMAL(6,4) COMMENT '估值状态 0~1（越高=越贵）',
    industry_cycle DECIMAL(6,4) COMMENT '行业周期位置 0~1',
    earnings_trend DECIMAL(6,4) COMMENT '盈利趋势 0~1',
    price_trend DECIMAL(6,4) COMMENT '价格趋势 0~1',
    expectation DECIMAL(6,4) COMMENT '市场预期强度 0~1',
    macro_regime DECIMAL(6,4) COMMENT '宏观状态 0~1',
    market_regime DECIMAL(6,4) COMMENT 'Market Precondition 0~1',
    confidence DECIMAL(6,4) COMMENT 'Precondition 置信度',
    detail JSON,
    computed_at DATETIME,
    UNIQUE KEY uk_stock_time (stock_id, computed_at),
    KEY idx_stock (stock_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3) score_weight_config：动态权重配置（版本化，第 13 节）
CREATE TABLE IF NOT EXISTS score_weight_config (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    version VARCHAR(64) COMMENT '权重版本号',
    weights JSON COMMENT '{"fundamental":0.30,"precondition":0.25,"market":0.15,"news":0.15,"prediction":0.15}',
    regime VARCHAR(32) DEFAULT 'all' COMMENT '适用市场状态 all/risk_on/risk_off',
    active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_version (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) score_snapshot：历史评分快照（第 25 节 Backtest 数据基础）
CREATE TABLE IF NOT EXISTS score_snapshot (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    stock_id BIGINT UNSIGNED,
    score DECIMAL(6,2) COMMENT 'Overall Score 0~100',
    confidence DECIMAL(6,4) COMMENT '0~1',
    direction VARCHAR(16) COMMENT 'STRONG_BULLISH/BULLISH/NEUTRAL/BEARISH/STRONG_BEARISH',
    weight_version VARCHAR(64),
    snapshot_time DATETIME,
    forward_return_5d DECIMAL(8,4) COMMENT '回填：5日后实际收益',
    forward_return_20d DECIMAL(8,4) COMMENT '回填：20日后实际收益',
    KEY idx_stock_time (stock_id, snapshot_time),
    KEY idx_time (snapshot_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) score_component：评分拆解（每个 snapshot 的成分分 + 权重 + 贡献）
CREATE TABLE IF NOT EXISTS score_component (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    snapshot_id BIGINT UNSIGNED,
    component VARCHAR(32) COMMENT 'fundamental/precondition/market/news/prediction',
    score DECIMAL(6,4) COMMENT '成分分 0~100',
    weight DECIMAL(6,4) COMMENT '实际使用权重',
    contribution DECIMAL(6,4) COMMENT 'score*weight',
    KEY idx_snapshot (snapshot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6) signal_conflict：冲突信号记录（第 12 节）
CREATE TABLE IF NOT EXISTS signal_conflict (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    stock_id BIGINT UNSIGNED,
    domains VARCHAR(128) COMMENT '冲突域，如 fundamental,market',
    severity DECIMAL(6,4) COMMENT '0~1 严重度',
    description VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_stock (stock_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7) calibration_run：校准运行记录（Phase 8 主表）
CREATE TABLE IF NOT EXISTS calibration_run (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    run_type VARCHAR(32) COMMENT 'ic_weight/confidence/threshold',
    horizon_days INT COMMENT '前瞻窗口 5/20',
    sample_count INT,
    ic_mean DECIMAL(8,4) COMMENT '平均信息系数',
    weight_version_from VARCHAR(64),
    weight_version_to VARCHAR(64),
    status VARCHAR(16),
    detail JSON,
    run_time DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8) calibration_component：每个成分的校准结果（IC + 新旧权重）
CREATE TABLE IF NOT EXISTS calibration_component (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT UNSIGNED,
    component VARCHAR(32),
    ic DECIMAL(8,4) COMMENT '信息系数（Spearman）',
    old_weight DECIMAL(6,4),
    new_weight DECIMAL(6,4),
    accepted TINYINT DEFAULT 0 COMMENT '是否采纳',
    KEY idx_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
