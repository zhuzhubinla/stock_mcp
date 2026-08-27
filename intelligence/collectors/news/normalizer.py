"""Normalizer：把 provider 原始输出规范化为 NewsItem（防御性清洗）"""
from .providers.base import NewsItem


def normalize(raw, provider_code="finnhub"):
    """dict/NewsItem -> NewsItem；无法识别或缺少标题返回 None"""
    if isinstance(raw, NewsItem):
        return raw
    if isinstance(raw, dict):
        item = NewsItem(
            source_news_id=str(raw.get("source_news_id") or raw.get("id") or ""),
            title=(raw.get("title") or raw.get("headline") or "").strip(),
            summary=raw.get("summary") or "",
            content=raw.get("content") or raw.get("summary") or "",
            url=raw.get("url") or "",
            image_url=raw.get("image_url") or raw.get("image") or "",
            author=raw.get("author") or "",
            publisher=raw.get("publisher") or raw.get("source") or provider_code,
            language=raw.get("language") or "en",
            published_at=raw.get("published_at"),
        )
        return item if item.title else None
    return None
