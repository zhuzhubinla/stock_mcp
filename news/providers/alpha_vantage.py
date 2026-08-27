"""Alpha Vantage 新闻源实现（NEWS_SENTIMENT 接口，免费额度 25 次/天、5 次/分）"""
from datetime import datetime, timezone

import requests

from config import ALPHAVANTAGE_API_KEY
from .base import NewsProvider, NewsItem


class AlphaVantageProvider(NewsProvider):
    code = "alphavantage"
    name = "Alpha Vantage"
    base_url = "https://www.alphavantage.co"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(ALPHAVANTAGE_API_KEY)

    def get_news(self, symbol, start_time, end_time):
        if not ALPHAVANTAGE_API_KEY:
            raise RuntimeError("未配置 ALPHAVANTAGE_API_KEY")

        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": symbol,
            "apikey": ALPHAVANTAGE_API_KEY,
            "limit": 50,
        }
        # time_from/time_to 格式 YYYYMMDDTHHMM（可选，不传则返回最近新闻）
        r = requests.get(f"{self.base_url}/query", params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if "feed" not in data:
            # 限流/错误信息在顶层 Note / Information
            note = data.get("Note") or data.get("Information") or str(data)[:200]
            raise RuntimeError(f"Alpha Vantage 返回异常: {note}")

        items = []
        for n in data.get("feed", []):
            ts = n.get("time_published") or ""
            published_at = None
            if ts:
                try:
                    published_at = datetime.strptime(ts, "%Y%m%dT%H%M%S").replace(tzinfo=None)
                except ValueError:
                    published_at = None
            items.append(NewsItem(
                source_news_id=str(n.get("url") or ""),
                title=n.get("title") or "",
                summary=n.get("summary") or "",
                content=n.get("summary") or "",
                url=n.get("url") or "",
                image_url=n.get("banner_image") or "",
                author=", ".join(n.get("authors") or []),
                publisher=n.get("source") or "Alpha Vantage",
                language="en",
                published_at=published_at,
            ))
        return items
