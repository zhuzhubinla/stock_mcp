"""Phase 7 Macro→Industry Transmission 迁移执行器（幂等，可重复运行）
建 7 张表 + 专家先验 seed（因子/行业补齐/敏感性/传导边）。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn

SQL_FILE = "/home/admin/stock_agent/migrations/20260903_phase7_macro_transmission.sql"
TABLES = ["macro_factor", "macro_industry_exposure", "macro_transmission_edge",
          "industry_transmission_event", "industry_macro_score",
          "macro_factor_signal", "macro_regime"]


def main():
    sql = open(SQL_FILE, encoding="utf-8").read()
    # 去掉纯注释行，避免注释粘连导致语句头不识别
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    cleaned = "\n".join(lines)
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]

    with get_conn() as conn, conn.cursor() as cur:
        for stmt in statements:
            head = stmt.upper()
            if not (head.startswith("CREATE") or head.startswith("INSERT")):
                continue
            cur.execute(stmt)
        print("[ok] 迁移语句全部执行")
        for t in TABLES:
            cur.execute(f"SELECT COUNT(*) c FROM {t}")
            print(f"    {t}: {cur.fetchone()['c']} rows")
        cur.execute("SELECT code, name FROM industry WHERE code IN "
                    "('software','banks','consumer','energy')")
        print("    新增行业:", [r["code"] for r in cur.fetchall()])
    print("[done] Phase 7 迁移完成")


if __name__ == "__main__":
    main()
