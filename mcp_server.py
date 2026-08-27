"""Stock Agent MCP Server - V2
核心 Tool：quote / history / news / fundamentals / technical / analyze
新闻体系（Phase5）：summary / events / sentiment / impact / anomalies / explain_price_move
数据优先 MySQL 缓存，过期后从 Finnhub 刷新；新闻走采集+AI 分析管线。

Intelligence Graph（Phase6）：stock_first / industry_first / factor_first / chain / relationship / drivers
"""
import sys
sys.path.append("/home/admin/stock_agent")

from fastmcp import FastMCP
from intelligence.services import stock_service
from intelligence.services import stock_first, industry_first, factor_first
from intelligence.stock.resolver import resolve
from intelligence.company.profile import profile
from intelligence.business.decomposer import decompose
from intelligence.industry.mapper import map_company, map_industry, industry_tree
from intelligence.supply_chain.mapper import get_chain, upstream, downstream, chain_for_company
from intelligence.relationship.explorer import explore
from intelligence.factor.engine import drivers, industry_factors, indicators, supply_demand
from intelligence.financial_model.engine import build_revenue_model, run_scenarios
from intelligence.valuation.engine import estimate
from intelligence.ai.analyst import summarize

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
    return build_revenue_model(symbol.upper())


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


if __name__ == "__main__":
    mcp.run()
