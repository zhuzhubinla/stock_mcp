-- ============================================================
-- Stock Agent Intelligence Graph 迁移（2026-08-27）
-- 依据《Stock Agent Intelligence Graph 架构》第 5 / 18 节
-- 新增表：company / business_segment / industry / industry_chain
--         industry_chain_node / industry_chain_edge / company_relationship
--         industry_factor / industry_indicator / supply_demand
--         industry_company / financial_driver / financial_model
--         industry_forecast / company_forecast / valuation
--         source / source_document / event
-- 全部 CREATE TABLE IF NOT EXISTS，幂等可重复执行
-- ============================================================

-- 1) 公司主体（上市/非上市）
CREATE TABLE IF NOT EXISTS company (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    stock_symbol VARCHAR(20) NULL COMMENT '上市证券代码，非上市为空',
    name VARCHAR(255) NOT NULL,
    legal_name VARCHAR(255),
    country VARCHAR(50),
    exchange VARCHAR(20),
    listed TINYINT DEFAULT 1,
    sector VARCHAR(100),
    description TEXT,
    source_id BIGINT UNSIGNED NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_name (name),
    KEY idx_stock_symbol (stock_symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) 行业（层级分类）
CREATE TABLE IF NOT EXISTS industry (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    level INT DEFAULT 1 COMMENT '1=大行业 2=子行业 3=细分',
    parent_id BIGINT UNSIGNED NULL,
    description TEXT,
    UNIQUE KEY uk_code (code),
    KEY idx_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3) 业务分拆（Company → Business Segment → Industry）
CREATE TABLE IF NOT EXISTS business_segment (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    industry_id BIGINT UNSIGNED NULL,
    revenue_share DECIMAL(5,4) COMMENT '占总营收比例 0-1',
    is_primary TINYINT DEFAULT 0,
    UNIQUE KEY uk_company_segment (company_id, name),
    KEY idx_industry (industry_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) 产业链
CREATE TABLE IF NOT EXISTS industry_chain (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    UNIQUE KEY uk_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) 产业链节点（晶圆制造/封测/SoC/品牌...）
CREATE TABLE IF NOT EXISTS industry_chain_node (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    chain_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    node_type VARCHAR(50) COMMENT 'upstream/midstream/downstream/end_market',
    description TEXT,
    UNIQUE KEY uk_chain_node (chain_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6) 产业链上下游关系（有向边）
CREATE TABLE IF NOT EXISTS industry_chain_edge (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    chain_id BIGINT UNSIGNED NOT NULL,
    from_node_id BIGINT UNSIGNED NOT NULL,
    to_node_id BIGINT UNSIGNED NOT NULL,
    relation_type VARCHAR(50) DEFAULT 'supplies',
    UNIQUE KEY uk_edge (chain_id, from_node_id, to_node_id),
    KEY idx_chain (chain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7) 公司关系（供应商/客户/竞争对手/伙伴/foundry...）
CREATE TABLE IF NOT EXISTS company_relationship (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    related_company_id BIGINT UNSIGNED NOT NULL,
    relation_type VARCHAR(30) NOT NULL COMMENT 'supplier/customer/competitor/partner/foundry/packaging/manufacturer/distributor/joint_venture',
    importance DECIMAL(5,4) COMMENT '0-1',
    confidence DECIMAL(5,4) COMMENT '0-1',
    effective_date DATE NULL,
    expire_date DATE NULL,
    source_id BIGINT UNSIGNED NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_relationship (company_id, related_company_id, relation_type),
    KEY idx_related (related_company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8) 行业因子（需求/价格/成本/政策/技术驱动）
CREATE TABLE IF NOT EXISTS industry_factor (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    factor_type VARCHAR(30) COMMENT 'demand/price/cost/policy/technology',
    direction VARCHAR(10) DEFAULT 'positive' COMMENT 'positive/negative',
    description TEXT,
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_factor (industry_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9) 行业指标（出货量/渗透率/ASP/产能/库存）
CREATE TABLE IF NOT EXISTS industry_indicator (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    indicator_name VARCHAR(100) NOT NULL,
    value DECIMAL(20,4),
    unit VARCHAR(30),
    period VARCHAR(20),
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_indicator_period (industry_id, indicator_name, period),
    KEY idx_indicator (industry_id, indicator_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10) 供需（产能/产量/需求/库存/缺口）
CREATE TABLE IF NOT EXISTS supply_demand (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    period VARCHAR(20) NOT NULL,
    capacity DECIMAL(20,4),
    production DECIMAL(20,4),
    demand DECIMAL(20,4),
    inventory DECIMAL(20,4),
    gap DECIMAL(20,4) COMMENT '缺口 = demand - production',
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_sd (industry_id, period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11) 行业-公司 多对多暴露
CREATE TABLE IF NOT EXISTS industry_company (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    company_id BIGINT UNSIGNED NOT NULL,
    exposure DECIMAL(5,4) DEFAULT 1.0000 COMMENT '暴露度 0-1',
    role VARCHAR(50) COMMENT '公司在产业链中的角色',
    source_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uk_industry_company (industry_id, company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12) 财务驱动（Driver → Revenue/Margin/EPS 映射）
CREATE TABLE IF NOT EXISTS financial_driver (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    business_segment_id BIGINT UNSIGNED NULL,
    driver_type VARCHAR(30) COMMENT 'demand/price/cost/policy/technology',
    driver_name VARCHAR(255) NOT NULL,
    source_indicator_id BIGINT UNSIGNED NULL COMMENT '对应 industry_indicator.id',
    impact_metric VARCHAR(50) COMMENT 'revenue/gross_margin/operating_margin/eps/fcf',
    impact_direction VARCHAR(10) COMMENT 'positive/negative',
    impact_coefficient DECIMAL(12,4) COMMENT '指标变动1% → 影响幅度',
    base_value DECIMAL(20,4),
    forecast_value DECIMAL(20,4),
    confidence DECIMAL(5,4),
    source_id BIGINT UNSIGNED NULL,
    KEY idx_company (company_id),
    KEY idx_segment (business_segment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 13) 公司预测（Revenue/EPS/FCF）
CREATE TABLE IF NOT EXISTS company_forecast (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    business_segment_id BIGINT UNSIGNED NULL,
    metric VARCHAR(30) NOT NULL COMMENT 'revenue/eps/fcf/gross_margin',
    period VARCHAR(20) NOT NULL COMMENT '2026A/2026E/2027E',
    value DECIMAL(20,4),
    confidence DECIMAL(5,4),
    model VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_forecast (company_id, business_segment_id, metric, period, model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 14) 行业预测
CREATE TABLE IF NOT EXISTS industry_forecast (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    industry_id BIGINT UNSIGNED NOT NULL,
    indicator_name VARCHAR(100) NOT NULL,
    period VARCHAR(20) NOT NULL,
    value DECIMAL(20,4),
    confidence DECIMAL(5,4),
    model VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_industry_forecast (industry_id, indicator_name, period, model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 15) 财务模型（Bull/Base/Bear 情景）
CREATE TABLE IF NOT EXISTS financial_model (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    scenario VARCHAR(10) NOT NULL COMMENT 'bull/base/bear',
    period VARCHAR(20) NOT NULL,
    revenue DECIMAL(20,4),
    gross_profit DECIMAL(20,4),
    operating_income DECIMAL(20,4),
    net_income DECIMAL(20,4),
    eps DECIMAL(12,4),
    fcf DECIMAL(20,4),
    model VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_finmodel (company_id, scenario, period, model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 16) 估值（PE/PS/DCF/EV-EBITDA/目标价）
CREATE TABLE IF NOT EXISTS valuation (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id BIGINT UNSIGNED NOT NULL,
    method VARCHAR(30) NOT NULL COMMENT 'PE/PS/DCF/EV_EBITDA/target_price',
    scenario VARCHAR(10),
    value DECIMAL(20,4),
    target_price DECIMAL(12,4),
    as_of DATE,
    model VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_company (company_id, as_of)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 17) 数据源
CREATE TABLE IF NOT EXISTS source (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(500),
    source_type VARCHAR(50) COMMENT 'api/document/web',
    UNIQUE KEY uk_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 18) 源文档（10-K/10-Q/研报等）
CREATE TABLE IF NOT EXISTS source_document (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT UNSIGNED NOT NULL,
    doc_type VARCHAR(50),
    title VARCHAR(1000),
    url VARCHAR(2000),
    published_at DATETIME,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_source (source_id),
    KEY idx_published (published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 19) 通用事件（区别于 stock_news_event，服务事件驱动分析）
CREATE TABLE IF NOT EXISTS event (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_document_id BIGINT UNSIGNED NULL,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(1000),
    description TEXT,
    event_time DATETIME,
    impact_score DECIMAL(6,4),
    confidence DECIMAL(6,4),
    status VARCHAR(30) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_event_type (event_type),
    KEY idx_event_time (event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
