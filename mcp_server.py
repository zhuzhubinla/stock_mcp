"""Stock Agent MCP Server - V2
核心 Tool：quote / history / news / fundamentals / technical / analyze
新闻体系（Phase5）：summary / events / sentiment / impact / anomalies / explain_price_move
数据优先 MySQL 缓存，过期后从 Finnhub 刷新；新闻走采集+AI 分析管线。

Intelligence Graph（Phase6）：stock_first / industry_first / factor_first / chain / relationship / drivers
"""
import sys
sys.path.append("/home/admin/stock_agent")

from fastmcp import FastMCP
from data.adapters import stock_service
from app.use_cases import stock_first, industry_first, factor_first
from domain.stock.resolver import resolve
from domain.company.profile import profile
from domain.business.decomposer import decompose
from domain.industry.mapper import map_company, map_industry, industry_tree
from domain.supply_chain.mapper import get_chain, upstream, downstream, chain_for_company
from domain.relationship.explorer import explore
from domain.factor.engine import drivers, industry_factors, indicators, supply_demand
from financial_model.revenue import build_revenue_model as build_revenue_model_func
from financial_model.scenario import run_scenarios
from financial_model.valuation import estimate
from ai.analyst import summarize

mcp = FastMCP("stock-server")


@mcp.tool()
def stock_get_quote(symbol: str) -> dict:
    """获取指定股票实时/最近行情（价格、涨跌幅、高低开）"""
    return stock_service.get_quote(symbol.upper())


@mcp.tool()
def stock_get_history(symbol: str, days: int = 90) -> dict:
    """获取指定股票历史 OHLCV 日线数据"""
    return stock_service.get_history(symbol.upper(), days=days)


@mcp.tool()
def stock_get_news(symbol: str, limit: int = 5, hours: int = None) -> dict:
    """获取指定股票近期新闻（含 AI 分析：情绪/影响度/事件类型）"""
    return stock_service.get_news(symbol.upper(), limit=limit, hours=hours)


@mcp.tool()
def stock_get_news_summary(symbol: str, hours: int = 24) -> dict:
    """新闻汇总：数量、总体情绪、高影响事件（AI 分析结果）"""
    return stock_service.get_news_summary(symbol.upper(), hours=hours)


@mcp.tool()
def stock_get_news_events(symbol: str, hours: int = 24, event_type: str = None) -> dict:
    """按事件类型聚合的新闻事件（earnings/m_and_a/macro/guidance 等）"""
    return stock_service.get_news_events(symbol.upper(), hours=hours, event_type=event_type)


@mcp.tool()
def stock_get_news_sentiment(symbol: str, hours: int = 24) -> dict:
    """新闻情绪统计：正/负/中性分布"""
    return stock_service.get_news_sentiment(symbol.upper(), hours=hours)


@mcp.tool()
def stock_get_news_impact(symbol: str, hours: int = 24) -> dict:
    """高影响新闻列表（按 impact_score 降序）"""
    return stock_service.get_news_impact(symbol.upper(), hours=hours)


@mcp.tool()
def stock_get_fundamentals(symbol: str) -> dict:
    """获取指定股票基本面指标（PE、利润率、增长等）"""
    return stock_service.get_fundamentals(symbol.upper())


@mcp.tool()
def stock_get_technical(symbol: str, days: int = 120) -> dict:
    """获取指定股票技术指标（RSI、MACD、均线、波动率、量比）"""
    return stock_service.get_technical(symbol.upper(), days=days)


@mcp.tool()
def stock_analyze(symbol: str) -> dict:
    """综合分析指定股票：汇总行情/技术/新闻/基本面，输出 Signal Engine 评分与明细"""
    return stock_service.analyze(symbol.upper())


@mcp.tool()
def stock_get_anomalies(symbol: str, days: int = 30) -> dict:
    """价格/成交量异常检测，附窗口内高影响新闻事件（归因）"""
    return stock_service.get_anomalies(symbol.upper(), days=days)


@mcp.tool()
def stock_explain_price_move(symbol: str, days: int = 10) -> dict:
    """解释最近一次异常波动的原因（价格异常 + 新闻归因）"""
    return stock_service.explain_price_move(symbol.upper(), days=days)


# ============================================================
# Intelligence Graph（Phase6）
# ============================================================

@mcp.tool()
def stock_intelligence_analyze(symbol: str, with_valuation: bool = True) -> dict:
    """【Stock-First】个股反向推理全链路：
    Stock→Company→Business→Industry→Supply Chain→Drivers→Financial Model→Valuation
    回答"为什么涨/跌、业务怎么拆、产业链上下游、驱动因子、情景EPS、目标价"""
    return stock_first.analyze(symbol.upper(), with_valuation=with_valuation)


@mcp.tool()
def stock_intelligence_company_profile(symbol: str) -> dict:
    """公司画像：主体信息 + 业务分拆 + 所属行业暴露 + 历史估值"""
    return profile(symbol=symbol.upper())


@mcp.tool()
def stock_intelligence_business_segments(symbol: str) -> dict:
    """业务分拆：公司各业务线及其映射行业、营收占比"""
    return decompose(symbol=symbol.upper())


@mcp.tool()
def stock_intelligence_industry_map(symbol: str) -> dict:
    """个股 → 行业反向映射（经业务分拆与行业暴露双路径）"""
    return map_company(symbol.upper())


@mcp.tool()
def stock_intelligence_industry_analyze(name: str = None, code: str = None) -> dict:
    """【Industry-First】行业选股：行业因子/指标/供需/预测 + 受益公司排名"""
    return industry_first.analyze(name=name, code=code)


@mcp.tool()
def stock_intelligence_industry_companies(industry_id: int = None, code: str = None,
                                          name: str = None) -> dict:
    """行业 → 公司列表（按暴露度排序）"""
    return map_industry(industry_id=industry_id, code=code, name=name)


@mcp.tool()
def stock_intelligence_industries() -> dict:
    """行业层级树（1级行业 + 子行业）"""
    return {"industries": industry_tree()}


@mcp.tool()
def stock_intelligence_factor_impact(indicator_name: str = None, new_value: float = None,
                                     industry_id: int = None) -> dict:
    """【Factor-First】指标/事件变化 → 行业公司财务影响 → 弹性排名
    例：DRAM 合约价上涨 20% 谁最受益"""
    return factor_first.analyze_indicator(indicator_name=indicator_name,
                                          industry_id=industry_id, new_value=new_value)


@mcp.tool()
def stock_intelligence_factor_analyze(factor_name: str, industry_id: int = None) -> dict:
    """行业因子详情 + 关联指标（需求/价格/成本/政策/技术驱动）"""
    return factor_first.analyze_factor(factor_name, industry_id=industry_id)


@mcp.tool()
def stock_intelligence_chain(name: str = None) -> dict:
    """产业链全图：节点 + 上下游边（如 AI 眼镜产业链）"""
    return get_chain(name=name)


@mcp.tool()
def stock_intelligence_chain_upstream(name: str, node: str, depth: int = 2) -> dict:
    """产业链某节点的上游追踪（供应商/原材料/设备）"""
    chain = get_chain(name=name)
    if "error" in chain:
        return chain
    return upstream(chain["chain_id"], node, depth=depth)


@mcp.tool()
def stock_intelligence_chain_downstream(name: str, node: str, depth: int = 2) -> dict:
    """产业链某节点的下游追踪（客户/品牌/终端需求）"""
    chain = get_chain(name=name)
    if "error" in chain:
        return chain
    return downstream(chain["chain_id"], node, depth=depth)


@mcp.tool()
def stock_intelligence_chain_for_company(symbol: str) -> dict:
    """个股 → 所属产业链（按业务/行业反查）"""
    return chain_for_company(symbol.upper())


@mcp.tool()
def stock_intelligence_relationships(symbol: str, relation_type: str = None) -> dict:
    """公司关系：供应商/客户/竞争对手/伙伴/foundry 等（带重要性/置信度）"""
    return explore(symbol=symbol.upper(), relation_type=relation_type)


@mcp.tool()
def stock_intelligence_drivers(symbol: str, impact_metric: str = None) -> dict:
    """公司财务驱动：行业因子 → 收入/毛利率/EPS 的映射（含影响系数）"""
    return drivers(symbol=symbol.upper(), impact_metric=impact_metric)


@mcp.tool()
def stock_intelligence_financial_model(symbol: str) -> dict:
    """营收模型：分业务 Shipment×Share×ASP 拆解"""
    return build_revenue_model_func(symbol.upper())


@mcp.tool()
def stock_intelligence_scenarios(symbol: str, period: str = "2026E") -> dict:
    """Bull/Base/Bear 情景 EPS 预测"""
    return run_scenarios(symbol.upper(), period=period)


@mcp.tool()
def stock_intelligence_valuation(symbol: str, period: str = "2026E") -> dict:
    """估值：情景 EPS × 行业 PE → 目标价区间"""
    return estimate(symbol.upper(), period=period)


@mcp.tool()
def stock_intelligence_report(symbol: str) -> dict:
    """LLM 研究报告：对 Stock-First 全链路结果生成中文研报摘要"""
    sf = stock_first.analyze(symbol.upper(), with_valuation=True)
    return summarize(stock_first_result=sf, symbol=symbol.upper())


# ============================================================
# 领域工具（Detailed Technical Design 第 26 节规范命名）
# ============================================================

@mcp.tool()
def resolve_stock(ticker: str) -> dict:
    """定位股票与公司主体（Stock Resolver）"""
    return resolve(ticker.upper())


@mcp.tool()
def get_company_profile(ticker: str) -> dict:
    """公司画像：主体信息 + 业务分拆 + 行业暴露 + 估值记录"""
    return profile(symbol=ticker.upper())


@mcp.tool()
def get_business_segments(ticker: str) -> dict:
    """业务分拆：公司各业务线及其映射行业、营收占比"""
    return decompose(symbol=ticker.upper())


@mcp.tool()
def get_industry_exposure(ticker: str) -> dict:
    """公司对行业的暴露度（exposure_weight / revenue / profit 暴露）"""
    return map_company(ticker.upper())


@mcp.tool()
def get_supply_chain(chain_name: str = None) -> dict:
    """产业链全图：节点 + 上下游边"""
    return get_chain(name=chain_name)


@mcp.tool()
def get_upstream_companies(chain_name: str, node: str, depth: int = 2) -> dict:
    """产业链某节点上游追踪（供应商/原材料/设备）"""
    chain = get_chain(name=chain_name)
    if "error" in chain:
        return chain
    return upstream(chain["chain_id"], node, depth=depth)


@mcp.tool()
def get_downstream_companies(chain_name: str, node: str, depth: int = 2) -> dict:
    """产业链某节点下游追踪（客户/品牌/终端需求）"""
    chain = get_chain(name=chain_name)
    if "error" in chain:
        return chain
    return downstream(chain["chain_id"], node, depth=depth)


@mcp.tool()
def get_company_relationships(ticker: str, relationship_type: str = None) -> dict:
    """公司关系：supplier/customer/competitor/partner/foundry..."""
    return explore(symbol=ticker.upper(), relation_type=relationship_type)


@mcp.tool()
def get_industry_factors(industry_id: int = None, factor_type: str = None) -> dict:
    """行业驱动因子（demand/price/cost/technology/policy/macro/competition/capacity）"""
    return {"factors": industry_factors(industry_id=industry_id, factor_type=factor_type)}


@mcp.tool()
def get_industry_indicators(industry_id: int = None, indicator_code: str = None,
                            ticker: str = None) -> dict:
    """行业指标（出货量/渗透率/ASP/产能/库存），可按行业或个股反查"""
    return {"indicators": indicators(industry_id=industry_id, indicator_code=indicator_code,
                                     symbol=ticker.upper() if ticker else None)}


@mcp.tool()
def get_supply_demand(industry_id: int = None) -> dict:
    """供需：产能/产量/需求/库存/利用率/缺口"""
    return {"supply_demand": supply_demand(industry_id=industry_id)}


@mcp.tool()
def get_company_events(ticker: str, event_type: str = None, hours: int = 168) -> dict:
    """公司事件（新闻/政策/产品发布/产能变化），事件驱动分析入口"""
    from data.repositories.forecast_repo import get_events
    company = profile(symbol=ticker.upper())
    if "error" in company:
        return company
    rows = get_events(event_type=event_type, company_id=company["company_id"], hours=hours)
    return {"symbol": ticker.upper(), "count": len(rows), "events": rows}


@mcp.tool()
def get_financials(ticker: str) -> dict:
    """公司基本面指标（PE/利润率/增长/ROE 等）"""
    return stock_service.get_fundamentals(ticker.upper())


@mcp.tool()
def build_revenue_model(ticker: str) -> dict:
    """分业务营收模型：Revenue = Σ Shipment × Share × ASP"""
    return build_revenue_model_func(ticker.upper())


@mcp.tool()
def run_scenario(ticker: str, period: str = "2026") -> dict:
    """Bull/Base/Bear 情景 EPS 预测"""
    return run_scenarios(ticker.upper(), period=period)


@mcp.tool()
def run_valuation(ticker: str, period: str = "2026") -> dict:
    """估值：情景 EPS × 行业 PE → 目标价区间"""
    return estimate(ticker.upper(), period=period)


@mcp.tool()
def generate_research_report(ticker: str) -> dict:
    """LLM 研究报告：对 Stock-First 全链路结果生成中文研报摘要"""
    sf = stock_first.analyze(ticker.upper(), with_valuation=True)
    return summarize(stock_first_result=sf, symbol=ticker.upper())


@mcp.tool()
def industry_sync(symbols: str = None) -> dict:
    """手动触发真实行业数据同步：SEC 财报 + FRED 行业指标（替换种子数据）"""
    from jobs.industry_sync import run_industry_sync
    sym_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    return run_industry_sync(symbols=sym_list)


@mcp.tool()
def get_sec_financials(symbol: str) -> dict:
    """获取公司 SEC XBRL 真实财报（营收/净利/EPS/现金流，年度）"""
    from data.collectors.sec_financials import get_annual_metrics
    return get_annual_metrics(symbol.upper())


# ============================================================
# Phase 8：Investment Intelligence + Online Learning（设计文档第 7/13/14/23/26 节）
# ============================================================

@mcp.tool()
def stock_intelligence_v2(symbol: str, with_valuation: bool = True) -> dict:
    """【Phase 8 全链路】Investment Intelligence Pipeline：
    Market Regime → Data Engine → Precondition(Context Vector + Market Precondition)
    → Expectation Gap → Signal → Conflict/Confidence → Dynamic Scoring(0-100)
    → Scenario/Valuation → Risk/Reward → Snapshot（在线学习数据）"""
    from app.use_cases.intelligence_pipeline import intelligence
    return intelligence(symbol.upper(), persist=True, with_valuation=with_valuation)


@mcp.tool()
def stock_get_market_regime(force_refresh: bool = False) -> dict:
    """Market Regime：当前市场状态（risk_on/risk_off/neutral + 趋势/波动/宽度/宏观分）"""
    from context.regime_detector import detect_regime, get_latest_regime
    if force_refresh:
        return detect_regime(persist=True)
    return get_latest_regime()


@mcp.tool()
def stock_get_precondition(symbol: str, refresh: bool = False) -> dict:
    """Precondition / Context Vector：估值/行业周期/盈利趋势/价格趋势/预期/宏观/Market Precondition
    Context 是信号的调节条件，不是简单加分项"""
    from context.precondition_engine import build_context
    if refresh:
        return build_context(symbol.upper(), persist=True)
    from context.precondition_engine import get_context
    rows = get_context(symbol.upper(), limit=1)
    if rows:
        r = rows[0]
        return {"symbol": symbol.upper(),
                "context_vector": {k: float(r[k]) for k in
                                    ("valuation", "industry_cycle", "earnings_trend",
                                     "price_trend", "expectation", "macro_regime",
                                     "market_regime")},
                "confidence": float(r["confidence"]),
                "computed_at": str(r["computed_at"])}
    return build_context(symbol.upper(), persist=True)


@mcp.tool()
def stock_get_expectation(symbol: str) -> dict:
    """Expectation Gap：Actual vs Expected vs Priced-in（超预期/预期透支）"""
    from context.expectation_engine import expectation_gap
    return expectation_gap(symbol.upper())


@mcp.tool()
def stock_get_score(symbol: str, refresh: bool = False) -> dict:
    """【Phase 8】Overall Score：0-100 动态加权评分 + 置信度 + 方向 + 成分拆解
    refresh=True 时重新跑全链路并生成新快照"""
    if refresh:
        from app.use_cases.intelligence_pipeline import intelligence
        r = intelligence(symbol.upper(), persist=True)
        return {"symbol": symbol.upper(), "overall_score": r["overall_score"],
                "confidence": r["confidence"], "direction": r["direction"],
                "market_regime": r.get("market_regime"),
                "snapshot_id": r.get("snapshot_id"),
                "components": next((s["data"]["components"] for s in r["steps"]
                                    if s["step"] == "dynamic_scoring"), []),
                "computed_at": r.get("computed_at")}
    from scoring.score_engine import get_snapshot_history
    rows = get_snapshot_history(symbol.upper(), limit=1)
    if not rows:
        return {"symbol": symbol.upper(), "error": "无快照，请用 refresh=True 生成"}
    r = rows[0]
    return {"symbol": symbol.upper(), "overall_score": float(r["score"]),
            "confidence": float(r["confidence"]), "direction": r["direction"],
            "weight_version": r["weight_version"],
            "snapshot_time": str(r["snapshot_time"]),
            "components": [{"component": c["component"], "score": float(c["score"]),
                            "weight": float(c["weight"])} for c in r.get("components", [])]}


@mcp.tool()
def stock_get_score_history(symbol: str, limit: int = 30) -> dict:
    """评分历史快照（回测数据）：总分/置信度/方向/成分/已回填 forward return"""
    from scoring.score_engine import get_snapshot_history
    rows = get_snapshot_history(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(rows), "snapshots": rows}


@mcp.tool()
def stock_get_conflicts(symbol: str, limit: int = 20) -> dict:
    """信号冲突记录（fundamental vs market / news vs industry 等）"""
    from signals.conflict import get_conflicts
    rows = get_conflicts(symbol.upper(), limit=limit)
    return {"symbol": symbol.upper(), "count": len(rows), "conflicts": rows}


@mcp.tool()
def stock_run_calibration(horizon_days: int = 20, dry_run: bool = False) -> dict:
    """【Phase 8】Online Learning / Continuous Calibration：
    回填 forward return → 计算各成分 IC（Spearman）→ 在线更新动态权重（版本化）
    dry_run=True 只预览不落库"""
    from learning.online_calibration import run_calibration
    return run_calibration(horizon_days=horizon_days, persist=not dry_run)


@mcp.tool()
def stock_get_calibration(limit: int = 10) -> dict:
    """校准历史：IC / 权重版本变更 / 各成分调权记录"""
    from learning.online_calibration import get_calibration_history
    return {"runs": get_calibration_history(limit=limit)}


@mcp.tool()
def stock_get_weight_config() -> dict:
    """当前动态权重配置（版本化，Phase 8 在线学习产物）"""
    from scoring.weight_engine import get_weight_config, list_weight_versions
    cfg = get_weight_config()
    return {"active": cfg, "versions": list_weight_versions()}


@mcp.tool()
def stock_replay_history() -> dict:
    """【Phase 8 初始化】历史重放：用历史价格生成带真实 forward return 的校准样本
    （仅首次搭建时使用，正常在线学习靠每日快照自然积累）"""
    from learning.history_replay import replay_watchlist
    return replay_watchlist(persist=True)


# ============================================================
# Prediction Intelligence（设计文档第 8 节：Polymarket/Kalshi 真实数据）
# ============================================================

@mcp.tool()
def prediction_sync(source: str = "kalshi", limit: int = 30, proxy: str = None) -> dict:
    """同步预测市场数据：Kalshi（大陆可直连 demo API）/ Polymarket（需海外 VPS 或代理）
    拉取事件+市场+概率 → 落库"""
    from data.collectors.prediction.collector import collect_source
    return collect_source(source, limit=limit, persist=True, proxy=proxy)


@mcp.tool()
def prediction_events(category: str = None, status: str = "open", limit: int = 50) -> dict:
    """预测事件列表（宏观/公司/AI/加密/选举等分类）"""
    from data.repositories import prediction_repo as repo
    evs = repo.list_events(status=status, category=category, limit=limit)
    return {"count": len(evs), "events": [
        {"id": e["id"], "title": e["title"], "category": e["category"],
         "status": e["status"], "end_time": str(e["end_time"]) if e.get("end_time") else None}
        for e in evs]}


@mcp.tool()
def prediction_markets(status: str = "active", source_code: str = None, limit: int = 50) -> dict:
    """预测市场列表（含实时概率/流动性/成交量）"""
    from data.repositories import prediction_repo as repo
    ms = repo.list_markets(status=status, source_code=source_code, limit=limit)
    return {"count": len(ms), "markets": [
        {"id": m["id"], "title": m.get("title"), "source": m.get("source_code"),
         "probability": float(m["last_price"]) if m.get("last_price") is not None else None,
         "open_interest": float(m["open_interest"]) if m.get("open_interest") is not None else None,
         "event": m.get("event_title"), "category": m.get("event_category")}
        for m in ms]}


@mcp.tool()
def prediction_consensus(event_id: int = None, category: str = None) -> dict:
    """多源共识：Σ(P_i×W_i)/Σ(W_i) + 源离散度 + 24h/7d 概率动量
    event_id 指定单事件，否则按类别计算全部"""
    from domain.prediction.engine import compute_consensus, compute_all_consensus
    if event_id:
        c = compute_consensus(event_id, persist=True)
        return c or {"event_id": event_id, "error": "无共识（事件无有效市场）"}
    return {"results": compute_all_consensus(persist=True, category=category)}


@mcp.tool()
def prediction_signals(symbol: str = None, limit: int = 50) -> dict:
    """Prediction→Stock 映射信号：预测事件经 Knowledge Graph 传播到个股
    例：AI CapEx→Data Center→GPU→NVDA；symbol 指定则返回该股预测聚合分"""
    from data.repositories import prediction_repo as repo
    from domain.prediction.mapper import stock_prediction_score
    if symbol:
        return stock_prediction_score(symbol.upper())
    rows = repo.get_signals(limit=limit)
    return {"count": len(rows), "signals": [
        {"entity": r["entity_symbol"], "type": r["entity_type"],
         "direction": r["direction"], "strength": float(r["strength"]),
         "confidence": float(r["confidence"]), "probability": float(r["probability"]) if r.get("probability") is not None else None,
         "event": r.get("event_title"), "path": r.get("propagation_path")}
        for r in rows]}


@mcp.tool()
def prediction_map_events() -> dict:
    """对全部 open 预测事件执行 → 股票映射（Knowledge Graph 传播）"""
    from domain.prediction.mapper import map_all_events
    return map_all_events(persist=True)


if __name__ == "__main__":
    mcp.run()
