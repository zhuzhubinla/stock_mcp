"""Stock Resolver：symbol → stock → company
Agent 流程第 1 步。负责解析证券代码并定位公司主体。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from database import mysql_db as db
from intelligence.repositories import graph_repo


def resolve(symbol):
    """输入 ticker，返回 {stock, company} 结构；公司不存在时尝试自动建主体"""
    symbol = symbol.upper().strip()
    stock = db.get_stock(symbol)
    if not stock:
        # 自动注册 stock 记录（保持旧表兼容）
        db.upsert_stock(symbol)
        stock = db.get_stock(symbol)

    company = graph_repo.get_company(symbol=symbol)
    if not company:
        company_id = graph_repo.upsert_company(
            stock_symbol=symbol, name=symbol,
            exchange=stock.get("exchange") if stock else None,
            sector=stock.get("sector") if stock else None,
        )
        company = graph_repo.get_company(company_id=company_id)
        # 回写 stock.company_id
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE stock SET company_id=%s WHERE symbol=%s",
                        (company_id, symbol))

    return {"symbol": symbol, "stock": stock, "company": company,
            "company_id": company["id"]}
