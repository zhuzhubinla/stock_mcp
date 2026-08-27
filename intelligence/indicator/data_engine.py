"""Data Engine：数据获取与刷新（行情/历史/新闻/基本面 + 行业数据）
Agent 流程第 8 步。复用既有 services.stock_service 与 news 管线。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from services import stock_service


def market_data(symbol, force_refresh=False):
    """个股行情/历史/基本面/技术面"""
    return {
        "quote": stock_service.get_quote(symbol, force_refresh=force_refresh),
        "fundamentals": stock_service.get_fundamentals(symbol, force_refresh=force_refresh),
        "technical": stock_service.get_technical(symbol, force_refresh=force_refresh),
    }


def news_data(symbol, limit=5, hours=24, force_refresh=False):
    """个股新闻（含 AI 分析）"""
    return stock_service.get_news(symbol, limit=limit, hours=hours,
                                  force_refresh=force_refresh)


def price_history(symbol, days=120, force_refresh=False):
    return stock_service.get_history(symbol, days=days, force_refresh=force_refresh)
