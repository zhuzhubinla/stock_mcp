-- ============================================================
-- Stock Agent Phase5.1 新闻源扩展：新增 Alpha Vantage / Benzinga / SEC
-- 幂等：INSERT IGNORE（uk_source_code 保证不重复）
-- ============================================================

INSERT IGNORE INTO news_source (name, code, api_type, base_url, enabled, priority)
VALUES
('Alpha Vantage', 'alphavantage', 'alphavantage', 'https://www.alphavantage.co', 1, 20),
('Benzinga', 'benzinga', 'benzinga', 'https://api.benzinga.com', 1, 30),
('SEC EDGAR', 'sec', 'sec', 'https://data.sec.gov', 1, 40);
