"""Business Decomposer：公司 → 业务分拆（避免多元化公司被简单归到单一行业）
Agent 流程第 3 步。从 business_segment 表读取；缺数据时给出提示。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories import graph_repo


def decompose(company_id=None, symbol=None):
    """返回公司业务分拆列表（含映射行业）"""
    segments = graph_repo.get_business_segments(company_id=company_id, symbol=symbol)
    if not segments:
        return {"count": 0, "segments": [], "note": "暂无业务分拆数据，请先 seed"}
    out = []
    for s in segments:
        out.append({
            "segment_id": s["id"],
            "name": s["name"],
            "description": s.get("description"),
            "industry_id": s.get("industry_id"),
            "industry": s.get("industry_name"),
            "industry_code": s.get("industry_code"),
            "revenue_share": float(s["revenue_share"]) if s.get("revenue_share") is not None else None,
            "is_primary": s.get("is_primary"),
        })
    return {"company": segments[0]["company_name"] if segments else None,
            "symbol": segments[0]["stock_symbol"] if segments else symbol,
            "count": len(out), "segments": out}
