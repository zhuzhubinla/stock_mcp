"""Intelligence Graph 迁移执行器（幂等：CREATE TABLE IF NOT EXISTS，可重复执行）
用法：python3 migrations/run_intelligence_graph.py
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn

SQL_FILE = "/home/admin/stock_agent/migrations/20260827_intelligence_graph.sql"

NEW_TABLES = [
    "company", "industry", "business_segment", "industry_chain",
    "industry_chain_node", "industry_chain_edge", "company_relationship",
    "industry_factor", "industry_indicator", "supply_demand",
    "industry_company", "financial_driver", "company_forecast",
    "industry_forecast", "financial_model", "valuation",
    "source", "source_document", "event",
]


def table_exists(cur, name):
    cur.execute("SHOW TABLES LIKE %s", (name,))
    return cur.fetchone() is not None


def main():
    with get_conn() as conn, conn.cursor() as cur:
        sql = open(SQL_FILE, encoding="utf-8").read()
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            cur.execute(stmt)
        # 兼容：stock 表加 company_id 列（若缺失）
        cur.execute("SHOW COLUMNS FROM stock LIKE 'company_id'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE stock ADD COLUMN company_id BIGINT UNSIGNED NULL AFTER symbol")
            print("[ok] stock 表新增 company_id 列")
        # 验证
        for t in NEW_TABLES:
            print(f"    table {t}: {'存在' if table_exists(cur, t) else '缺失!'}")
        cur.execute("SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE()")
        print(f"[done] 当前库表总数: {cur.fetchone()['c']}")


if __name__ == "__main__":
    main()
