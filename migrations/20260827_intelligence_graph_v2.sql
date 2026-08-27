-- ============================================================
-- Stock Agent Intelligence Graph v2 迁移（2026-08-27）
-- 依据《Detailed Technical Design》第 5-14 节字段级设计
-- intelligence 域表全部 DROP 重建为设计版（数据为种子数据，可重跑 seed）
-- 不动真实数据表：stock_price / stock_news* / stock_fundamental / stock_signal / stock_analysis
-- ============================================================

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS company_relationship;
DROP TABLE IF EXISTS industry_company;
DROP TABLE IF EXISTS financial_driver;
DROP TABLE IF EXISTS financial_model_line;
DROP TABLE IF EXISTS financial_model;
DROP TABLE IF EXISTS company_forecast;
DROP TABLE IF EXISTS industry_forecast;
DROP TABLE IF EXISTS valuation;
DROP TABLE IF EXISTS industry_chain_node;
DROP TABLE IF EXISTS industry_chain_edge;
DROP TABLE IF EXISTS industry_chain;
DROP TABLE IF EXISTS supply_demand;
DROP TABLE IF EXISTS industry_indicator;
DROP TABLE IF EXISTS industry_factor;
DROP TABLE IF EXISTS business_segment;
DROP TABLE IF EXISTS industry;
DROP TABLE IF EXISTS company;
DROP TABLE IF EXISTS event;
DROP TABLE IF EXISTS source_document;
DROP TABLE IF EXISTS source;
DROP TABLE IF EXISTS data_quality_log;

SET FOREIGN_KEY_CHECKS = 1;

-- 1) stock（证券实体层：同一公司可多市场证券）
CREATE TABLE IF NOT EXISTS stock (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NULL,
    ticker VARCHAR(32) NOT NULL,
    exchange VARCHAR(32),
    market VARCHAR(32),
    currency VARCHAR(8) DEFAULT 'USD',
    security_type VARCHAR(32) DEFAULT 'stock',
    status VARCHAR(16) DEFAULT 'active',
    listed_date DATE NULL,
    delisted_date DATE NULL,
    name VARCHAR(100),
    sector VARCHAR(50),
    industry VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_exchange_ticker (exchange, ticker),
    KEY idx_company (company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) company
CREATE TABLE IF NOT EXISTS company (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    name_en VARCHAR(255),
    country VARCHAR(64),
    company_type VARCHAR(32) DEFAULT 'public',
    description TEXT,
    website VARCHAR(512),
    status VARCHAR(16) DEFAULT 'active',
    stock_symbol VARCHAR(20) NULL COMMENT '兼容旧逻辑：主上市代码',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_name (name),
    KEY idx_name_en (name_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3) business_segment（公司业务层：Company → Segment → Industry）
CREATE TABLE IF NOT EXISTS business_segment (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    segment_type VARCHAR(64),
    revenue_share DECIMAL(8,4),
    gross_margin DECIMAL(8,4) NULL,
    valid_from DATE NULL,
    valid_to DATE NULL,
    industry_id BIGINT UNSIGNED NULL COMMENT '主映射行业',
    is_primary TINYINT DEFAULT 0,
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_company_segment (company_id, name),
    KEY idx_segment_type (segment_type),
    KEY idx_industry (industry_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) industry（taxonomy+code 唯一）
CREATE TABLE IF NOT EXISTS industry (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    parent_id BIGINT UNSIGNED NULL,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    name_en VARCHAR(255),
    taxonomy VARCHAR(64) DEFAULT 'custom',
    level INT DEFAULT 1,
    description TEXT,
    status VARCHAR(16) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_taxonomy_code (taxonomy, code),
    KEY idx_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) industry_company（暴露度模型：exposure_weight + revenue/profit 暴露）
CREATE TABLE IF NOT EXISTS industry_company (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    company_id BIGINT UNSIGNED NOT NULL,
    business_segment_id BIGINT UNSIGNED NULL,
    role VARCHAR(64),
    exposure_weight DECIMAL(8,4) DEFAULT 1.0000,
    revenue_exposure DECIMAL(8,4) NULL,
    profit_exposure DECIMAL(8,4) NULL,
    confidence DECIMAL(5,4),
    effective_date DATE NULL,
    expire_date DATE NULL,
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_industry_company (industry_id, company_id, business_segment_id),
    KEY idx_company (company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6) industry_chain（绑定行业）
CREATE TABLE IF NOT EXISTS industry_chain (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    UNIQUE KEY uk_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7) industry_chain_node（树形：parent_node_id + position）
CREATE TABLE IF NOT EXISTS industry_chain_node (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    chain_id BIGINT UNSIGNED NOT NULL,
    parent_node_id BIGINT UNSIGNED NULL,
    name VARCHAR(255) NOT NULL,
    node_type VARCHAR(64) COMMENT 'raw_material/equipment/wafer/packaging/chip/component/assembly/brand/channel/end_market',
    position INT DEFAULT 0,
    description TEXT,
    UNIQUE KEY uk_chain_node (chain_id, name),
    KEY idx_parent (parent_node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8) industry_chain_edge（上下游边，保留图遍历能力）
CREATE TABLE IF NOT EXISTS industry_chain_edge (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    chain_id BIGINT UNSIGNED NOT NULL,
    from_node_id BIGINT UNSIGNED NOT NULL,
    to_node_id BIGINT UNSIGNED NOT NULL,
    relation_type VARCHAR(50) DEFAULT 'supplies',
    UNIQUE KEY uk_edge (chain_id, from_node_id, to_node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9) company_relationship（+industry_id/chain_node_id/description）
CREATE TABLE IF NOT EXISTS company_relationship (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    related_company_id BIGINT UNSIGNED NOT NULL,
    relationship_type VARCHAR(64) NOT NULL,
    industry_id BIGINT UNSIGNED NULL,
    chain_node_id BIGINT UNSIGNED NULL,
    importance DECIMAL(5,4),
    confidence DECIMAL(5,4),
    description TEXT,
    effective_date DATE NULL,
    expire_date DATE NULL,
    source_id BIGINT UNSIGNED NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_relationship (company_id, related_company_id, relationship_type),
    KEY idx_related (related_company_id, relationship_type),
    KEY idx_chain_node (chain_node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10) industry_factor（factor_type 8 类 + impact_direction + importance + unit）
CREATE TABLE IF NOT EXISTS industry_factor (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    factor_type VARCHAR(64) COMMENT 'demand/price/cost/technology/policy/macro/competition/capacity',
    description TEXT,
    impact_direction VARCHAR(16) DEFAULT 'positive',
    importance DECIMAL(5,4),
    unit VARCHAR(32),
    source_id BIGINT UNSIGNED NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_factor (industry_id, name),
    KEY idx_factor_type (factor_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11) industry_indicator（indicator_code + period DATE + frequency）
CREATE TABLE IF NOT EXISTS industry_indicator (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    indicator_code VARCHAR(128) NOT NULL,
    indicator_name VARCHAR(255) NOT NULL,
    period DATE,
    value DECIMAL(24,8),
    unit VARCHAR(32),
    frequency VARCHAR(16) DEFAULT 'yearly',
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_indicator (industry_id, indicator_code, period, source_id),
    KEY idx_code_period (indicator_code, period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12) supply_demand（+utilization_rate/supply_demand_gap/unit）
CREATE TABLE IF NOT EXISTS supply_demand (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    period DATE,
    capacity DECIMAL(24,8) NULL,
    production DECIMAL(24,8) NULL,
    demand DECIMAL(24,8) NULL,
    inventory DECIMAL(24,8) NULL,
    utilization_rate DECIMAL(10,6) NULL,
    supply_demand_gap DECIMAL(24,8) NULL,
    unit VARCHAR(32),
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_sd (industry_id, period),
    KEY idx_period (period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 13) financial_driver（+factor_id/indicator_id/elasticity）
CREATE TABLE IF NOT EXISTS financial_driver (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    business_segment_id BIGINT UNSIGNED NULL,
    factor_id BIGINT UNSIGNED NULL,
    indicator_id BIGINT UNSIGNED NULL,
    driver_name VARCHAR(255) NOT NULL,
    impact_metric VARCHAR(64) COMMENT 'revenue/gross_margin/operating_margin/eps/fcf',
    impact_direction VARCHAR(16),
    impact_coefficient DECIMAL(20,8) NULL,
    elasticity DECIMAL(20,8) NULL,
    base_value DECIMAL(24,8) NULL,
    forecast_value DECIMAL(24,8) NULL,
    confidence DECIMAL(5,4),
    effective_date DATE NULL,
    expire_date DATE NULL,
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_driver (company_id, business_segment_id, driver_name, impact_metric, indicator_id),
    KEY idx_factor (factor_id),
    KEY idx_indicator (indicator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 14) financial_model（模型头：版本/基期/预测区间）
CREATE TABLE IF NOT EXISTS financial_model (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255),
    model_type VARCHAR(64) DEFAULT 'bottom_up',
    version VARCHAR(32) DEFAULT 'v1',
    base_period DATE NULL,
    forecast_start DATE NULL,
    forecast_end DATE NULL,
    status VARCHAR(16) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_company (company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 15) financial_model_line（模型明细行：metric/period/value/assumption/source_driver/formula）
CREATE TABLE IF NOT EXISTS financial_model_line (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    model_id BIGINT UNSIGNED NOT NULL,
    business_segment_id BIGINT UNSIGNED NULL,
    metric VARCHAR(64) COMMENT 'shipment/asp/revenue/cogs/gross_profit/opex/operating_profit/net_income/eps/fcf',
    period DATE,
    value DECIMAL(24,8),
    assumption_type VARCHAR(32) COMMENT 'input/derived/scenario',
    source_driver_id BIGINT UNSIGNED NULL,
    formula TEXT NULL,
    KEY idx_model_metric (model_id, metric, period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 16) industry_forecast（+scenario/low/high/model_version）
CREATE TABLE IF NOT EXISTS industry_forecast (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    indicator_code VARCHAR(128) NOT NULL,
    period DATE,
    scenario VARCHAR(32) DEFAULT 'base',
    value DECIMAL(24,8),
    low_value DECIMAL(24,8) NULL,
    high_value DECIMAL(24,8) NULL,
    confidence DECIMAL(5,4),
    model_version VARCHAR(64),
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_industry_forecast (industry_id, indicator_code, period, scenario, model_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 17) company_forecast（+scenario/low/high/model_version）
CREATE TABLE IF NOT EXISTS company_forecast (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    business_segment_id BIGINT UNSIGNED NULL,
    metric VARCHAR(64) NOT NULL,
    period DATE,
    scenario VARCHAR(32) DEFAULT 'base',
    value DECIMAL(24,8),
    low_value DECIMAL(24,8) NULL,
    high_value DECIMAL(24,8) NULL,
    model_version VARCHAR(64),
    confidence DECIMAL(5,4),
    UNIQUE KEY uk_company_forecast (company_id, business_segment_id, metric, period, scenario, model_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 18) valuation（+valuation_date/upside/assumption_json）
CREATE TABLE IF NOT EXISTS valuation (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    model_type VARCHAR(32) COMMENT 'PE/PS/EV_EBITDA/DCF/FCF/Sum_of_Parts',
    valuation_date DATE,
    scenario VARCHAR(32),
    fair_value DECIMAL(24,8),
    upside DECIMAL(10,6),
    assumption_json JSON NULL,
    model_version VARCHAR(64),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_company_date (company_id, valuation_date),
    KEY idx_model_scenario (model_type, scenario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 19) source（+source_type/provider/reliability_score）
CREATE TABLE IF NOT EXISTS source (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_type VARCHAR(32) DEFAULT 'api',
    provider VARCHAR(64),
    name VARCHAR(255) NOT NULL,
    base_url VARCHAR(500),
    reliability_score DECIMAL(5,4) DEFAULT 0.5,
    UNIQUE KEY uk_code (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 20) source_document（+document_type/content_hash/raw_path）
CREATE TABLE IF NOT EXISTS source_document (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(1000),
    url VARCHAR(2000),
    published_at DATETIME,
    document_type VARCHAR(50),
    content_hash CHAR(64),
    raw_path VARCHAR(1000),
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_source (source_id),
    KEY idx_published (published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 21) event（+company_id/industry_id/impact_direction/source_document_id）
CREATE TABLE IF NOT EXISTS event (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    title VARCHAR(1000),
    event_date DATETIME,
    company_id BIGINT UNSIGNED NULL,
    industry_id BIGINT UNSIGNED NULL,
    impact_direction VARCHAR(16),
    impact_score DECIMAL(6,4),
    description TEXT,
    source_document_id BIGINT UNSIGNED NULL,
    status VARCHAR(30) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_event_type (event_type),
    KEY idx_event_date (event_date),
    KEY idx_company (company_id),
    KEY idx_industry (industry_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 22) data_quality_log（数据质量体系：可靠度/置信度/新鲜度/一致性/异常/血缘）
CREATE TABLE IF NOT EXISTS data_quality_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT UNSIGNED NULL,
    entity_type VARCHAR(64),
    entity_id BIGINT UNSIGNED NULL,
    check_name VARCHAR(64) COMMENT 'freshness/consistency/outlier/lineage',
    status VARCHAR(16) COMMENT 'pass/warn/fail',
    score DECIMAL(5,4),
    detail TEXT,
    checked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_entity (entity_type, entity_id),
    KEY idx_checked (checked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
