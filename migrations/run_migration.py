"""Phase5 新闻架构迁移执行器（幂等，可重复运行）
状态机：
  A. stock_news_symbol 存在 且 stock_news 存在  -> 已完成，跳过
  B. stock_news 存在（旧 schema，有 symbol 列）  -> 先改名 legacy
  C. legacy 存在 / stock_news 缺失（中间态）      -> 建表 + 迁移数据
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn

SQL_FILE = "/home/admin/stock_agent/migrations/20260823_news_phase5.sql"


def table_exists(cur, name):
    cur.execute("SHOW TABLES LIKE %s", (name,))
    return cur.fetchone() is not None


def main():
    with get_conn() as conn, conn.cursor() as cur:
        legacy = table_exists(cur, "stock_news_legacy")
        news = table_exists(cur, "stock_news")
        sym = table_exists(cur, "stock_news_symbol")

        if sym and news:
            print("[skip] 新架构已就绪（stock_news + stock_news_symbol 存在）")
            _verify(cur)
            return
        if not news and not legacy:
            print("[error] stock_news 与 stock_news_legacy 都不存在，无法迁移")
            return

        # 1) 旧表改名（旧 schema 判据：存在 symbol 列）
        if news and not legacy:
            cur.execute("SHOW COLUMNS FROM stock_news LIKE 'symbol'")
            if cur.fetchone():
                cur.execute("RENAME TABLE stock_news TO stock_news_legacy")
                print("[ok] RENAME stock_news -> stock_news_legacy")
                legacy = True
            else:
                print("[ok] stock_news 已是新 schema（无 symbol 列），跳过改名")
        elif news and legacy:
            print("[skip] 改名（legacy 已存在）")

        # 2) 按序执行 SQL 文件（RENAME 语句需跳过：要么已执行，要么不适用）
        sql = open(SQL_FILE, encoding="utf-8").read()
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            head = stmt.upper()
            if "RENAME TABLE" in head:
                if legacy:
                    print("[skip] RENAME（legacy 已存在）")
                else:
                    cur.execute(stmt)
                    print("[ok] RENAME stock_news -> stock_news_legacy")
                continue
            cur.execute(stmt)
            print(f"[ok] {stmt.splitlines()[-1][:60]}")

        _verify(cur)


def _verify(cur):
    for t in ["news_source", "stock_news", "stock_news_symbol",
              "stock_news_analysis", "stock_news_event", "news_fetch_log"]:
        print(f"    table {t}: {'存在' if table_exists(cur, t) else '缺失!'}")
    for t in ["stock_news", "stock_news_symbol", "news_source"]:
        cur.execute(f"SELECT COUNT(*) c FROM {t}")
        print(f"    {t} 行数: {cur.fetchone()['c']}")
    cur.execute("SELECT id, title FROM stock_news ORDER BY id LIMIT 3")
    for r in cur.fetchall():
        print(f"    样例: #{r['id']} {r['title'][:50]}")


if __name__ == "__main__":
    main()
