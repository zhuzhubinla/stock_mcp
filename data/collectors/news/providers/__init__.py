"""新闻源注册表：所有数据源在对应模块实现后注册即可"""
from .base import NewsItem, NewsProvider
from .finnhub import FinnhubProvider
from .alpha_vantage import AlphaVantageProvider
from .benzinga import BenzingaProvider
from .sec import SECProvider

PROVIDERS = {
    "finnhub": FinnhubProvider,
    "alphavantage": AlphaVantageProvider,
    "benzinga": BenzingaProvider,
    "sec": SECProvider,
}


def get_provider(code="finnhub") -> NewsProvider:
    cls = PROVIDERS.get(code)
    if cls is None:
        raise ValueError(f"未知新闻源: {code}，可用: {list(PROVIDERS)}")
    return cls()
