"""定时任务：新闻采集 + AI 分析"""
import json

from config import WATCHLIST_PATH, NEWS_ANALYZE_BATCH
from data.collectors.news.collector import collect
from data.collectors.news.analyzer import analyze_pending


def load_watchlist():
    try:
        with open(WATCHLIST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [s.upper() for s in data] if isinstance(data, list) else []
    except Exception as e:
        print(f"[news_update] 读取 watchlist 失败: {e}")
        return []


def collect_watchlist(hours=None):
    symbols = load_watchlist()
    if not symbols:
        return {"error": "watchlist 为空"}
    result = collect(symbols, hours=hours)
    print(f"[news_update] 采集: 源{result['sources']} 新增{result['inserted']} "
          f"重复{result['duplicated']} 错误{result['errors']}")
    return result


def analyze_pending_news(limit=None):
    result = analyze_pending(limit or NEWS_ANALYZE_BATCH)
    print(f"[news_update] 分析完成 {result}")
    return result
