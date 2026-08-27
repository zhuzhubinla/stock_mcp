"""定时任务：异常扫描（价格异常 + 新闻归因）"""
from datetime import datetime, timedelta

from config import ANOMALY_SCAN_DAYS
from news.anomaly import get_anomalies_with_causes
from tasks.news_task import load_watchlist


def scan_watchlist_anomalies(days=None):
    """扫描 watchlist 最近 N 天异常，返回近 3 天内的发现"""
    symbols = load_watchlist()
    findings = []
    cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    for symbol in symbols:
        try:
            data = get_anomalies_with_causes(symbol, days=days or ANOMALY_SCAN_DAYS)
        except Exception as e:
            print(f"[anomaly_task] {symbol} 扫描失败: {e}")
            continue
        for a in data["anomalies"]:
            if a["date"] >= cutoff:
                findings.append({
                    "symbol": symbol, "date": a["date"], "change_pct": a["change_pct"],
                    "volume_ratio": a["volume_ratio"], "reasons": a["reasons"],
                    "causes": [n["title"] for n in a.get("causes", [])[:3]],
                })
    print(f"[anomaly_task] 扫描完成，近3天发现 {len(findings)} 个异常")
    return {"findings": findings, "count": len(findings)}
