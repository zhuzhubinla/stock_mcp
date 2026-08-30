"""Prediction Intelligence 迁移执行器（幂等：CREATE TABLE IF NOT EXISTS，可重复执行）
用法：python3 migrations/run_prediction_intelligence.py
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn

SQL_FILE = "/home/admin/stock_agent/migrations/20260830_prediction_intelligence.sql"

NEW_TABLES = [
    "prediction_source", "prediction_event", "prediction_market",
    "prediction_outcome", "prediction_probability",
    "prediction_consensus", "prediction_signal",
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
        # 种子：prediction_source 配置
        cur.execute("""
            INSERT IGNORE INTO prediction_source (code, name, source_type, weight, reliability_score, enabled, priority)
            VALUES
              ('polymarket', 'Polymarket', 'api', 1.0, 0.75, 1, 'P0'),
              ('kalshi', 'Kalshi', 'api', 1.0, 0.80, 1, 'P0'),
              ('metaculus', 'Metaculus', 'api', 0.7, 0.65, 1, 'P1'),
              ('manifold', 'Manifold', 'api', 0.6, 0.55, 1, 'P1')
        """)
        missing = []
        for t in NEW_TABLES:
            ok = table_exists(cur, t)
            print(f"    table {t}: {'存在' if ok else '缺失!'}")
            if not ok:
                missing.append(t)
        cur.execute("SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE()")
        print(f"[done] 当前库表总数: {cur.fetchone()['c']}")
        cur.execute("SELECT code, weight, priority FROM prediction_source ORDER BY priority")
        for r in cur.fetchall():
            print(f"    source: {r['code']} weight={r['weight']} {r['priority']}")
        if missing:
            print(f"[error] 缺失表: {missing}")
        else:
            print("[ok] Prediction Intelligence 迁移完成")


if __name__ == "__main__":
    main()
