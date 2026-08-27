"""Company Profile：公司主体信息 + 基本面快照
Agent 流程第 2 步。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from intelligence.repositories import graph_repo, forecast_repo


def profile(company_id=None, symbol=None):
    """公司画像：主体信息 + 业务分拆 + 所属行业 + 最新估值记录"""
    company = graph_repo.get_company(company_id=company_id, symbol=symbol)
    if not company:
        return {"error": f"company not found: {symbol or company_id}"}

    segments = graph_repo.get_business_segments(company_id=company["id"])
    industries = graph_repo.get_industry_companies(symbol=company.get("stock_symbol"))
    valuations = forecast_repo.get_valuations(company_id=company["id"])

    return {
        "company_id": company["id"],
        "name": company["name"],
        "stock_symbol": company.get("stock_symbol"),
        "country": company.get("country"),
        "exchange": company.get("exchange"),
        "sector": company.get("sector"),
        "listed": company.get("listed"),
        "description": company.get("description"),
        "business_segments": segments,
        "industries": [{"industry_id": r["industry_id"], "industry": r["industry_name"],
                        "code": r["industry_code"], "exposure": float(r["exposure"] or 0),
                        "role": r["role"]} for r in industries],
        "valuations": valuations,
    }
