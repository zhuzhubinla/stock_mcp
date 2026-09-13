-- Stock Agent Phase 7：Macro → Industry Transmission Engine（2026-09-03）
-- 依据《Stock Agent Phase 7 — Industry Transmission Engine 设计文档》V1.0 §14
-- 文档指定 4 张核心表：
--   macro_industry_exposure / macro_transmission_edge
--   industry_transmission_event / industry_macro_score
-- 支撑表（工程必需，文档未明说但数据流需要）：
--   macro_factor            ：宏观因子主数据（文档 §5 八因子 + 文档 §10 示例用 DXY/AI_CAPEX）
--   macro_factor_signal     ：因子信号快照（文档 §4 数据流 Macro Signal [-1,+1]，可追溯+防泄露）
--   macro_regime            ：宏观四态 regime 快照（文档 §11）
-- 全部幂等可重复执行。专家先验 = 文档 §10 示例矩阵 + §8 示例传导路径。

-- ============ 1. 宏观因子主数据 ============
CREATE TABLE IF NOT EXISTS macro_factor (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(32) NOT NULL,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(16) DEFAULT 'core' COMMENT 'core=文档八因子 / aux=扩展',
    description VARCHAR(500),
    direction_note VARCHAR(500) COMMENT '因子信号+1 的宏观含义（消除符号歧义）',
    source VARCHAR(32) DEFAULT 'expert',
    model_version VARCHAR(64) DEFAULT 'v1',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观因子主数据（Phase 7）';

INSERT INTO macro_factor (code, name, category, description, direction_note)
SELECT * FROM (
    SELECT 'FED_POLICY' AS code, '联储政策' AS name, 'core', '联储政策与降息/加息预期', '+1 = 宽松/降息预期上升' UNION ALL
    SELECT 'INFLATION', '通胀', 'core', 'CPI/PCE/PPI/工资等通胀变量', '+1 = 通胀读数上行' UNION ALL
    SELECT 'LABOR', '就业', 'core', 'NFP/ADP/失业率/JOLTS/Claims/工资', '+1 = 就业市场走强' UNION ALL
    SELECT 'GROWTH', '经济增长', 'core', 'GDP/PMI/零售/工业产出', '+1 = 增长动能走强' UNION ALL
    SELECT 'RATES', '利率', 'core', '2Y/5Y/10Y/30Y、实际利率、收益率曲线', '+1 = 名义收益率上行' UNION ALL
    SELECT 'LIQUIDITY', '流动性', 'core', 'Fed 资产负债表/QT/QE/金融条件', '+1 = 流动性宽松' UNION ALL
    SELECT 'RISK', '风险偏好', 'core', 'VIX/信用利差/MOVE', '+1 = 风险偏好上升（VIX 下行）' UNION ALL
    SELECT 'COMMODITY', '大宗商品', 'core', 'WTI/天然气/铜', '+1 = 大宗价格上行' UNION ALL
    SELECT 'DXY', '美元指数', 'aux', '美元指数（文档 §10 示例因子）', '+1 = 美元走强' UNION ALL
    SELECT 'AI_CAPEX', 'AI资本开支', 'aux', 'AI CapEx（文档 §10 示例因子）', '+1 = AI 资本开支超预期'
) t
WHERE NOT EXISTS (SELECT 1 FROM macro_factor mf WHERE mf.code = t.code);

-- ============ 2. 行业树补齐（文档 §10 示例行业）============
-- 已在库：semiconductor(半导体)/cloud/edge_ai...；补齐 software/banks/consumer/energy
INSERT INTO industry (code, name, name_en, taxonomy, level, status)
SELECT * FROM (
    SELECT 'software' AS code, '软件' AS name, 'Software' AS name_en, 'custom' AS taxonomy, 1 AS level, 'active' AS status UNION ALL
    SELECT 'banks', '银行', 'Banks', 'custom', 1, 'active' UNION ALL
    SELECT 'consumer', '消费', 'Consumer', 'custom', 1, 'active' UNION ALL
    SELECT 'energy', '能源', 'Energy', 'custom', 1, 'active'
) t
WHERE NOT EXISTS (SELECT 1 FROM industry i WHERE i.code = t.code);

-- ============ 3. macro_industry_exposure（文档 §14.1）============
CREATE TABLE IF NOT EXISTS macro_industry_exposure (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    factor_id BIGINT UNSIGNED NOT NULL COMMENT '→ macro_factor.id',
    industry_id BIGINT UNSIGNED NOT NULL COMMENT '→ industry.id',
    sensitivity DECIMAL(10,6) NOT NULL COMMENT '因子上行对行业的敏感度，-1~+1（正=利好）',
    confidence DECIMAL(10,6) DEFAULT 0.5,
    source VARCHAR(32) DEFAULT 'expert',
    model_version VARCHAR(64) DEFAULT 'v1',
    regime VARCHAR(64) DEFAULT 'ALL' COMMENT 'ALL=全 regime 基础值；否则按 regime 覆盖',
    horizon VARCHAR(32) DEFAULT 'ALL',
    valid_from DATE NULL,
    valid_to DATE NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_factor_industry (factor_id, industry_id),
    INDEX idx_regime_horizon (regime, horizon),
    INDEX idx_industry (industry_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观因子→行业敏感性（Phase 7）';

-- 专家先验 V1（文档 §10 示例矩阵：10Y→RATES / Fed Policy→FED_POLICY / GDP→GROWTH）
INSERT INTO macro_industry_exposure
    (factor_id, industry_id, sensitivity, confidence, source, model_version, regime, horizon, valid_from)
SELECT mf.id, i.id, e.sensitivity, 0.60, 'expert', 'v1-expert', 'ALL', 'ALL', '2026-09-01'
FROM (
    SELECT 'semiconductor' AS ind_code, 'RATES' AS f_code, -0.75 AS sensitivity UNION ALL
    SELECT 'semiconductor', 'FED_POLICY', 0.70 UNION ALL
    SELECT 'semiconductor', 'GROWTH', 0.55 UNION ALL
    SELECT 'semiconductor', 'AI_CAPEX', 0.90 UNION ALL
    SELECT 'semiconductor', 'DXY', -0.30 UNION ALL
    SELECT 'software', 'RATES', -0.80 UNION ALL
    SELECT 'software', 'FED_POLICY', 0.75 UNION ALL
    SELECT 'software', 'GROWTH', 0.40 UNION ALL
    SELECT 'software', 'AI_CAPEX', 0.50 UNION ALL
    SELECT 'software', 'DXY', -0.25 UNION ALL
    SELECT 'banks', 'RATES', 0.70 UNION ALL
    SELECT 'banks', 'FED_POLICY', 0.10 UNION ALL
    SELECT 'banks', 'GROWTH', 0.60 UNION ALL
    SELECT 'banks', 'AI_CAPEX', 0.00 UNION ALL
    SELECT 'banks', 'DXY', 0.05 UNION ALL
    SELECT 'consumer', 'RATES', 0.10 UNION ALL
    SELECT 'consumer', 'FED_POLICY', 0.05 UNION ALL
    SELECT 'consumer', 'GROWTH', 0.75 UNION ALL
    SELECT 'consumer', 'AI_CAPEX', 0.00 UNION ALL
    SELECT 'consumer', 'DXY', -0.10 UNION ALL
    SELECT 'energy', 'RATES', 0.20 UNION ALL
    SELECT 'energy', 'FED_POLICY', -0.05 UNION ALL
    SELECT 'energy', 'GROWTH', 0.50 UNION ALL
    SELECT 'energy', 'AI_CAPEX', 0.00 UNION ALL
    SELECT 'energy', 'DXY', -0.40
) e
JOIN macro_factor mf ON mf.code = e.f_code
JOIN industry i ON i.code = e.ind_code
WHERE NOT EXISTS (
    SELECT 1 FROM macro_industry_exposure x
    WHERE x.factor_id = mf.id AND x.industry_id = i.id AND x.model_version = 'v1-expert'
      AND x.regime = 'ALL' AND x.horizon = 'ALL'
);

-- ============ 4. macro_transmission_edge（文档 §14.2）============
CREATE TABLE IF NOT EXISTS macro_transmission_edge (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_type VARCHAR(32) NOT NULL COMMENT 'macro_factor / macro_indicator / market_variable',
    source_id BIGINT UNSIGNED NOT NULL,
    target_type VARCHAR(32) NOT NULL COMMENT 'macro_factor / industry',
    target_id BIGINT UNSIGNED NOT NULL,
    weight DECIMAL(10,6) NOT NULL COMMENT '边权重（路径衰减前）',
    direction DECIMAL(10,6) DEFAULT 1 COMMENT '传导方向 ±1',
    confidence DECIMAL(10,6) DEFAULT 0.5,
    lag_minute INT DEFAULT 0,
    lag_max_minute INT DEFAULT 0,
    source VARCHAR(32) DEFAULT 'expert',
    model_version VARCHAR(64) DEFAULT 'v1',
    valid_from DATE NULL,
    valid_to DATE NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source (source_type, source_id),
    INDEX idx_target (target_type, target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观传导图边（Phase 7 Indirect Transmission）';

-- V1 专家路径（文档 §8 Indirect 示例：NFP→Labor→FedCut→2Y→10Y；以可用因子收敛为五条）
INSERT INTO macro_transmission_edge
    (source_type, source_id, target_type, target_id, weight, direction, confidence,
     lag_minute, lag_max_minute, source, model_version, valid_from)
SELECT 'macro_factor', s.id, 'macro_factor', t.id, e.weight, e.direction, e.confidence,
       e.lag_min, e.lag_max, 'expert', 'v1-expert', '2026-09-01'
FROM (
    SELECT 'macro_factor' AS type, 'INFLATION' AS code, 'macro_factor' AS ttype, 'FED_POLICY' AS tcode,
           0.60 AS weight, -1 AS direction, 0.80 AS confidence, 0 AS lag_min, 1440 AS lag_max UNION ALL
    SELECT 'macro_factor', 'FED_POLICY', 'macro_factor', 'RATES',
           0.70, -1, 0.85, 0, 4320 UNION ALL
    SELECT 'macro_factor', 'GROWTH', 'macro_factor', 'RATES',
           0.40, 1, 0.70, 0, 10080 UNION ALL
    SELECT 'macro_factor', 'LABOR', 'macro_factor', 'FED_POLICY',
           0.50, -1, 0.70, 0, 4320 UNION ALL
    SELECT 'macro_factor', 'COMMODITY', 'macro_factor', 'INFLATION',
           0.50, 1, 0.75, 0, 10080 UNION ALL
    SELECT 'macro_factor', 'RISK', 'macro_factor', 'RATES',
           0.35, -1, 0.55, 0, 4320
) e
JOIN macro_factor s ON s.code = e.code
JOIN macro_factor t ON t.code = e.tcode
WHERE NOT EXISTS (
    SELECT 1 FROM macro_transmission_edge x
    WHERE x.source_type = 'macro_factor' AND x.source_id = s.id
      AND x.target_type = 'macro_factor' AND x.target_id = t.id
      AND x.model_version = 'v1-expert'
);

-- ============ 5. industry_transmission_event（文档 §14.3）============
CREATE TABLE IF NOT EXISTS industry_transmission_event (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id BIGINT NOT NULL COMMENT '事件/情景 id（0=常规刷新；负值=情景 id 见 event_source）',
    event_source VARCHAR(32) DEFAULT 'macro_signal' COMMENT 'macro_signal / scenario / prediction',
    industry_id BIGINT UNSIGNED NOT NULL,
    impact_score DECIMAL(10,6),
    direction DECIMAL(10,6),
    confidence DECIMAL(10,6),
    explanation TEXT COMMENT 'JSON：因子分解与传导路径',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event_industry (event_id, industry_id),
    INDEX idx_industry (industry_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观事件/情景→行业传导结果（Phase 7）';

-- ============ 6. industry_macro_score（文档 §14.4）============
CREATE TABLE IF NOT EXISTS industry_macro_score (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    score_date DATETIME NOT NULL,
    horizon VARCHAR(32) NOT NULL COMMENT '1d / 1w / 1m / 3m',
    regime VARCHAR(64) COMMENT '计算时宏观 regime',
    score DECIMAL(10,6) COMMENT '行业宏观分，约 -1~+1（正=宏观顺风）',
    expected_return DECIMAL(12,6) COMMENT '预期收益%（启发式，待 Phase 8 校准）',
    confidence DECIMAL(10,6),
    model_version VARCHAR(64),
    detail JSON COMMENT '因子贡献分解',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_industry_date (industry_id, score_date, horizon, regime, model_version),
    INDEX idx_industry_date (industry_id, score_date),
    INDEX idx_horizon (horizon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业宏观分快照（Phase 7 → Phase 8 输入）';

-- ============ 7. 支撑表：因子信号 + 宏观 regime ============
CREATE TABLE IF NOT EXISTS macro_factor_signal (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    factor_id BIGINT UNSIGNED NOT NULL,
    signal_value DECIMAL(10,6) NOT NULL COMMENT '归一化信号 -1~+1',
    z_score DECIMAL(10,6) NULL,
    indicator_code VARCHAR(64) COMMENT '数据源 indicator_code（多源时取主源）',
    indicator_value DECIMAL(24,8) NULL,
    as_of DATE NULL COMMENT '数据时点（防泄露：<= 计算时刻可见数据）',
    source VARCHAR(16) DEFAULT 'fred',
    model_version VARCHAR(64) DEFAULT 'v1',
    detail JSON COMMENT '多源分解',
    computed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_factor_date (factor_id, as_of, source, model_version),
    INDEX idx_factor (factor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观因子信号快照（Phase 7）';

CREATE TABLE IF NOT EXISTS macro_regime (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    regime VARCHAR(32) COMMENT 'goldilocks / overheating / recession / stagflation / neutral',
    growth_yoy DECIMAL(10,6),
    inflation_yoy DECIMAL(10,6),
    growth_rising TINYINT,
    inflation_rising TINYINT,
    confidence DECIMAL(6,4),
    detail JSON,
    snapshot_time DATETIME,
    KEY idx_time (snapshot_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观四态 regime 快照（Phase 7）';
