"""Stock-First：个股反向推理（文档第 4 节）
Stock → Company → Business → Industry → Supply Chain → Drivers → Financial Model → Valuation
"""
import sys
sys.path.append("/home/admin/stock_agent")

from intelligence.stock.resolver import resolve
from intelligence.company.profile import profile
from intelligence.business.decomposer import decompose
from intelligence.industry.mapper import map_company
from intelligence.supply_chain.mapper import chain_for_company, get_chain
from intelligence.relationship.explorer import explore
from intelligence.factor.engine import drivers
from intelligence.financial_model.engine import build_revenue_model, run_scenarios
from intelligence.valuation.engine import estimate
from intelligence.indicator.data_engine import market_data, news_data


def analyze(symbol, with_valuation=True, persist=True):
    """完整 Stock-First 推理链，逐步输出"""
    symbol = symbol.upper()
    r = resolve(symbol)
    if not r.get("company"):
        return {"symbol": symbol, "error": "公司解析失败"}

    step = lambda name, data: {"step": name, "data": data}  # noqa
    chain = []

    # 1-2. Stock / Company
    chain.append(step("stock_resolver", {"symbol": symbol, "company_id": r["company_id"],
                                         "name": r["company"]["name"]}))
    prof = profile(company_id=r["company_id"])
    chain.append(step("company_profile", prof))

    # 3. Business Decomposer
    segs = decompose(company_id=r["company_id"])
    chain.append(step("business_decomposer", segs))

    # 4. Industry Mapper（反向：个股 → 行业）
    ind_map = map_company(symbol)
    chain.append(step("industry_mapper", ind_map))

    # 5. Chain Mapper（个股 → 产业链 → 上下游）
    chains = chain_for_company(symbol)
    chain_detail = []
    for c in chains.get("chains", []):
        ch = get_chain(name=c["chain"])
        if "error" not in ch:
            chain_detail.append(ch)
    chain.append(step("chain_mapper", {"chains": chains, "detail": chain_detail}))

    # 6. Relationship Explorer
    rel = explore(symbol=symbol)
    chain.append(step("relationship_explorer", rel))

    # 7. Driver Engine
    drv = drivers(symbol=symbol)
    chain.append(step("driver_engine", drv))

    # 8. Data Engine（行情/新闻/基本面）
    mkt = market_data(symbol)
    news = news_data(symbol, limit=5)
    chain.append(step("data_engine", {"market": {k: v for k, v in mkt.items()},
                                      "news": news}))

    # 9. Financial Model
    rev_model = build_revenue_model(symbol)
    chain.append(step("financial_model", rev_model))

    # 10. Scenario
    scen = run_scenarios(symbol, persist=persist)
    chain.append(step("scenario_engine", scen))

    # 11. Valuation
    val = estimate(symbol, persist=persist) if with_valuation else None
    if val:
        chain.append(step("valuation_engine", val))

    return {"symbol": symbol, "path": "Stock-First", "steps": chain,
            "step_count": len(chain)}
