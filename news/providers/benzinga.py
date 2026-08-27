"""Benzinga 新闻源实现（v2 News API）"""
from datetime import datetime, timezone

import requests

from config import BENZINGA_API_KEY
from .base import NewsProvider, NewsItem


class BenzingaProvider(NewsProvider):
    code = "benzinga"
    name = "Benzinga"
    base_url = "https://api.benzinga.com"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(BENZINGA_API_KEY)

    def get_news(self, symbol, start_time, end_time):
        if not BENZINGA_API_KEY:
            raise RuntimeError("未配置 BENZINGA_API_KEY")

        params = {
            "token": BENZINGA_API_KEY,
            "tickers": symbol,
            "date_from": start_time.strftime("%Y-%m-%d"),
            "date_to": end_time.strftime("%Y-%m-%d"),
            "page_size": 20,
            "display_output": "full",
        }
        r = requests.get(f"{self.base_url}/api/v2/news", params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise RuntimeError(f"Benzinga 返回异常: {str(data)[:200]}")

        items = []
        for n in data:
            created = n.get("created") or ""
            published_at = None
            if created:
                try:
                    # created 可能是 unix 秒或 ISO 字符串
                    published_at = datetime.fromtimestamp(float(created), tz=timezone.utc).replace(tzinfo=None)
                except (ValueError, TypeError):
                    try:
                        published_at = datetime.fromisoformat(str(created).replace("Z", "+00:00")).replace(tzinfo=None)
                    except ValueError:
                        published_at = None
            items.append(NewsItem(
                source_news_id=str(n.get("id") or ""),
                title=n.get("title") or "",
                summary=n.get("teaser") or "",
                content=n.get("body") or n.get("teaser") or "",
                url=n.get("url") or "",
                image_url=n.get("image") or "",
                author=n.get("author") or "",
                publisher="Benzinga",
                language="en",
                published_at = published_at,
            ))
        return items
