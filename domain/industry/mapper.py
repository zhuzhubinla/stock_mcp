"""Industry Mapper：业务/公司 ↔ 行业（多对多暴露）
Agent 流程第 4 步。支撑 Stock→Industry 反向映射与 Industry→Companies 行业选股。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories import graph_repo


def map_company(symbol):
    """公司 → 所属行业（经 business_segment + industry_company 双路径）"""
    industries = graph_repo.get_industry_companies(symbol=symbol)
    segs = graph_repo.get_business_segments(symbol=symbol)
    seg_industries = {}
    for s in segs:
        if s.get("industry_id"):
            seg_industries[s["name"]] = {
                "industry_id": s["industry_id"],
                "industry": s["industry_name"],
                "code": s["industry_code"],
            }
    return {
        "symbol": symbol,
        "via_industry_company": [{
            "industry_id": r["industry_id"], "industry": r["industry_name"],
            "code": r["industry_code"],
            "exposure_weight": float(r["exposure_weight"] or 0),
            "role": r["role"],
        } for r in industries],
        "via_business_segment": seg_industries,
    }


def map_industry(industry_id=None, code=None, name=None):
    """行业 → 公司列表（按暴露度排序）"""
    industry = graph_repo.get_industry(industry_id=industry_id, code=code, name=name)
    if not industry:
        return {"error": f"industry not found: {code or name or industry_id}"}
    companies = graph_repo.get_industry_companies(industry_id=industry["id"])
    return {
        "industry_id": industry["id"],
        "name": industry["name"],
        "code": industry["code"],
        "level": industry["level"],
        "parent_id": industry["parent_id"],
        "companies": [{
            "company_id": r["company_id"], "name": r["company_name"],
            "symbol": r["stock_symbol"],
            "exposure_weight": float(r["exposure_weight"] or 0),
            "role": r["role"],
        } for r in companies],
        "count": len(companies),
    }


def industry_tree():
    """行业层级树（1级行业 + 子行业）"""
    roots = graph_repo.list_industries(parent_id=None)
    tree = []
    for root in roots:
        children = graph_repo.list_industries(parent_id=root["id"])
        tree.append({
            "id": root["id"], "code": root["code"], "name": root["name"],
            "level": root["level"],
            "children": [{"id": c["id"], "code": c["code"], "name": c["name"],
                          "level": c["level"]} for c in children],
        })
    return tree
