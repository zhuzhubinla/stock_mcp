"""Relationship Explorer：公司关系（供应商/客户/竞争对手/伙伴/foundry...）
Agent 流程第 6 步。带 importance/confidence/有效期。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories import graph_repo


def explore(symbol=None, company_id=None, relation_type=None):
    """公司关系列表；relation_type 可过滤（supplier/customer/competitor/partner/foundry...）"""
    rows = graph_repo.get_relationships(company_id=company_id, symbol=symbol,
                                        relation_type=relation_type)
    out = [{
        "company": r["company_name"], "symbol": r["stock_symbol"],
        "related": r["related_name"], "related_symbol": r["related_symbol"],
        "relationship_type": r["relationship_type"],
        "importance": float(r["importance"]) if r["importance"] is not None else None,
        "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
        "effective_date": r["effective_date"], "expire_date": r["expire_date"],
    } for r in rows]
    return {"symbol": symbol, "relationship_type": relation_type,
            "count": len(out), "relationships": out}


def upstream_suppliers(symbol):
    """只取上游：supplier / foundry / packaging / manufacturer"""
    types = ("supplier", "foundry", "packaging", "manufacturer")
    rows = graph_repo.get_relationships(symbol=symbol)
    return [r for r in rows if r["relation_type"] in types]


def downstream_customers(symbol):
    """只取下游：customer / distributor"""
    rows = graph_repo.get_relationships(symbol=symbol)
    return [r for r in rows if r["relation_type"] in ("customer", "distributor")]
