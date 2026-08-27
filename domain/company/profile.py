"""Company Profile：公司主体信息 + 基本面快照
Agent 流程第 2 步。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories import graph_repo, forecast_repo


def profile(company_id=None, symbol=None):
    """公司画像：主体信息 + 业务分拆 + 所属行业 + 最新估值记录"""
    company = graph_repo.get_company(company_id=company_id, symbol=symbol)
    if not company:
        return {"error": f"company not found: {symbol or company_id}"}

    segments = graph_repo.get_business_segments(company_id=company["id"])
    industries = graph_repo.get_industry_companies(symbol=company.get("stock_symbol"))
    valuations = forecast_repo.get_valuations(company_id=company["id"])

    # sector 兜底：v2 company 表无 sector 列，从行业反推行业属性
    sector = company.get("sector")
    if not sector and industries:
        ind_names = " ".join(r["industry_name"] or "" for r in industries)
        ind_codes = " ".join(r["industry_code"] or "" for r in industries)
        combined = f"{ind_names} {ind_codes}"
        if any(k in combined for k in ("半导体", "芯片", "ai", "semiconductor", "chip", "memory", "cloud", "网络")):
            sector = "tech"
        elif any(k in combined for k in ("消费", "眼镜", "穿戴", "consumer")):
            sector = "consumer_electronics"
        else:
            sector = "general"

    return {
        "company_id": company["id"],
        "name": company["name"],
        "stock_symbol": company.get("stock_symbol"),
        "country": company.get("country"),
        "exchange": company.get("exchange"),
        "sector": sector,
        "listed": company.get("listed"),
        "description": company.get("description"),
        "business_segments": segments,
        "industries": [{"industry_id": r["industry_id"], "industry": r["industry_name"],
                        "code": r["industry_code"],
                        "exposure_weight": float(r["exposure_weight"] or 0),
                        "revenue_exposure": float(r["revenue_exposure"] or 0) if r.get("revenue_exposure") is not None else None,
                        "profit_exposure": float(r["profit_exposure"] or 0) if r.get("profit_exposure") is not None else None,
                        "role": r["role"]} for r in industries],
        "valuations": valuations,
    }
