"""Phase 8 Online Learning 迁移执行器（幂等：CREATE TABLE IF NOT EXISTS，可重复执行）
用法：python3 migrations/run_phase8_learning.py
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn

SQL_FILE = "/home/admin/stock_agent/migrations/20260830_phase8_online_learning.sql"

NEW_TABLES = [
    "market_regime", "stock_precondition", "score_weight_config",
    "score_snapshot", "score_component", "signal_conflict",
    "calibration_run", "calibration_component",
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
        # 验证
        missing = []
        for t in NEW_TABLES:
            ok = table_exists(cur, t)
            print(f"    table {t}: {'存在' if ok else '缺失!'}")
            if not ok:
                missing.append(t)
        cur.execute("SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE()")
        print(f"[done] 当前库表总数: {cur.fetchone()['c']}")
        if missing:
            print(f"[error] 缺失表: {missing}")
        else:
            print("[ok] Phase 8 迁移完成")


if __name__ == "__main__":
    main()
