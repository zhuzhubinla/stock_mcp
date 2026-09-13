"""定时调度：
- 08:30 每日简报（保留原逻辑）
- 每 15 分钟：watchlist 新闻采集 + AI 分析（Phase5）
- 每 60 分钟：watchlist 异常扫描 + 新闻归因
- 08:45 每日 Intelligence Graph 研报（Phase6）
- 数据更新策略（第 23 节）：
  日频 08:40 质量扫描；月频财务/预测更新（schedule 简化：每日跑，内部按需）
"""
import schedule
import time

from main import run
from jobs.news_update import collect_watchlist, analyze_pending_news
from jobs.industry_update import scan_watchlist_anomalies
from jobs.daily_sync import run_daily_intelligence_report
from jobs.quality_scan import run_quality_scan
from jobs.financial_update import run_financial_update
from jobs.forecast_update import run_forecast_update
from jobs.industry_sync import run_industry_sync
from learning.calibration_job import run_continuous_calibration
from jobs.prediction_sync import run_prediction_sync
from jobs.industry_macro_update import run_industry_macro_update

schedule.every().day.at("08:30").do(run)
schedule.every().day.at("08:40").do(run_quality_scan)
schedule.every().day.at("08:45").do(run_daily_intelligence_report)
schedule.every().day.at("08:50").do(run_industry_sync)
schedule.every().day.at("09:00").do(run_financial_update)
schedule.every().day.at("09:30").do(run_forecast_update)
schedule.every().day.at("09:45").do(run_prediction_sync)  # Prediction Intelligence：Kalshi/Polymarket 同步+映射
schedule.every().day.at("09:55").do(run_industry_macro_update)  # Phase 7：宏观信号+行业宏观分（依赖 08:50 FRED 同步）
schedule.every().day.at("18:00").do(run_continuous_calibration, horizon_days=20)  # Phase 8 每日校准
schedule.every(15).minutes.do(collect_watchlist)
schedule.every(15).minutes.do(analyze_pending_news)
schedule.every(60).minutes.do(scan_watchlist_anomalies)

if __name__ == "__main__":
    print("[cron] 调度已启动: 08:30简报/08:40质量/08:45研报/08:50行业同步/09:00财务/09:30预测/09:45预测市场同步/09:55宏观行业分(Phase7)/18:00在线校准/15min新闻/60min异常")
    while True:
        schedule.run_pending()
        time.sleep(60)
