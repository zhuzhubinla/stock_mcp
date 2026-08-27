"""Finnhub 新闻源实现"""
from datetime import datetime, timezone

import finnhub

from config import FINNHUB_API_KEY
from .base import NewsProvider, NewsItem


class FinnhubProvider(NewsProvider):
    code = "finnhub"
    name = "Finnhub"
    base_url = "https://finnhub.io"

    def __init__(self):
        self._client = finnhub.Client(api_key=FINNHUB_API_KEY)

    def get_news(self, symbol, start_time, end_time):
        result = self._client.company_news(
            symbol,
            start_time.strftime("%Y-%m-%d"),
            end_time.strftime("%Y-%m-%d"),
        ) or []
        items = []
        for n in result:
            ts = n.get("datetime") or 0
            published_at = None
            if ts:
                published_at = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            items.append(NewsItem(
                source_news_id=str(n.get("id") or ""),
                title=n.get("headline") or "",
                summary=n.get("summary") or "",
                content=n.get("summary") or "",
                url=n.get("url") or "",
                image_url=n.get("image") or "",
                publisher=n.get("source") or "Finnhub",
                language="en",
                published_at=published_at,
            ))
        return items
