"""定时调度：
- 08:30 每日简报（保留原逻辑）
- 每 15 分钟：watchlist 新闻采集 + AI 分析（Phase5）
- 每 60 分钟：watchlist 异常扫描 + 新闻归因
- 08:45 每日 Intelligence Graph 研报（Phase6）
"""
import schedule
import time

from main import run
from tasks.news_task import collect_watchlist, analyze_pending_news
from tasks.anomaly_task import scan_watchlist_anomalies
from intelligence.jobs.intelligence_job import run_daily_intelligence_report

schedule.every().day.at("08:30").do(run)
schedule.every().day.at("08:45").do(run_daily_intelligence_report)
schedule.every(15).minutes.do(collect_watchlist)
schedule.every(15).minutes.do(analyze_pending_news)
schedule.every(60).minutes.do(scan_watchlist_anomalies)

if __name__ == "__main__":
    print("[cron] 调度已启动: 每日08:30简报 / 08:45研报 / 15min新闻采集+分析 / 60min异常扫描")
    while True:
        schedule.run_pending()
        time.sleep(60)
