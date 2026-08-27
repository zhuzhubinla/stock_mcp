"""Provider 抽象层：统一新闻数据源接口，业务层不感知具体 API"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NewsItem:
    source_news_id: str = ""
    title: str = ""
    summary: str = ""
    content: str = ""
    url: str = ""
    image_url: str = ""
    author: str = ""
    publisher: str = ""
    language: str = "en"
    published_at: datetime = None


class NewsProvider(ABC):
    """所有新闻源实现统一接口。新增数据源时继承并实现 get_news 即可。"""

    code = "base"
    name = "Base"
    base_url = ""

    @classmethod
    def is_configured(cls) -> bool:
        """该源是否已配置可用（缺 API key 等返回 False，采集时自动跳过）"""
        return True

    @abstractmethod
    def get_news(self, symbol: str, start_time: datetime, end_time: datetime) -> list:
        """返回 list[NewsItem]"""
        raise NotImplementedError
