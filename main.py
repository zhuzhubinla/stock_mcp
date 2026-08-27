"""每日简报：采集新闻 → AI 分析 → 行情 → 推送（Webhook 未配置则只打印）"""
import json
from datetime import datetime

from config import WATCHLIST_PATH
from data.repositories import mysql_db as db
from data.adapters.stock_service import get_quote
from jobs.news_update import load_watchlist, collect_watchlist, analyze_pending_news
from data.adapters.wechat_push import send


def run():
    stocks = load_watchlist()
    if not stocks:
        print("[main] watchlist 为空")
        return
    collect_watchlist()
    analyze_pending_news(limit=20)

    lines = [f"📊 每日简报 {datetime.now():%Y-%m-%d %H:%M}"]
    for s in stocks:
        try:
            quote = get_quote(s)
        except Exception as e:
            print(f"[main] {s} 行情获取失败: {e}")
            continue
        news = db.get_news(s, limit=3)
        lines.append(f"\n=== {s} ===")
        lines.append(f"价格 {quote.get('price')}  涨跌 {quote.get('percent')}%")
        for n in news:
            imp = f" 影响度{float(n['impact_score']):.2f}" if n.get("impact_score") is not None else ""
            lines.append(f"· {n['title'][:60]}{imp}")
    report = "\n".join(lines)
    print(report)
    send(report)


if __name__ == "__main__":
    run()
