"""Prediction Source Adapter 基类（设计文档 8.3 统一流程：Source API → Adapter → Normalization）

所有预测源实现统一接口：
  fetch_events(limit)      → 事件列表（归一化）
  fetch_market(event_id)   → 市场详情（含概率/流动性）
  fetch_probability_history(market_id, hours) → 概率时序（Momentum 用）
  fetch_markets(limit)     → 直接拉市场列表（含价格）
"""
import sys
import abc

sys.path.append("/home/admin/stock_agent")


class PredictionAdapter(abc.ABC):
    """预测源适配器基类"""

    source_code = "base"

    def __init__(self, base_url=None, api_key=None, timeout=15, proxy=None):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.proxy = proxy

    # ---------- 统一归一化输出 ----------
    @staticmethod
    def _norm_event(ev):
        """归一化事件：{external_id, title, category, start_time, end_time, status}"""
        return ev

    @staticmethod
    def _norm_market(m):
        """归一化市场：{external_id, event_external_id, title, market_type, status,
        yes_ask, yes_bid, last_price, volume, open_interest, liquidity, close_time}"""
        return m

    # ---------- 子类实现 ----------
    @abc.abstractmethod
    def fetch_events(self, limit=20, status="open"):
        """拉取事件列表（归一化 dict 列表）"""

    @abc.abstractmethod
    def fetch_markets(self, limit=20, status="open"):
        """拉取市场列表（含价格，归一化 dict 列表）"""

    @abc.abstractmethod
    def fetch_market_detail(self, external_id):
        """拉取单个市场详情"""

    def fetch_probability_history(self, external_id, hours=24):
        """概率历史时序（默认不支持，子类覆写）"""
        return []

    # ---------- HTTP 工具 ----------
    def _get(self, url, params=None, headers=None):
        import requests
        h = {"User-Agent": "Mozilla/5.0 (stock-agent/1.0)"}
        if headers:
            h.update(headers)
        kw = dict(timeout=self.timeout, headers=h)
        if self.proxy:
            kw["proxies"] = {"http": self.proxy, "https": self.proxy}
        r = requests.get(url, params=params, **kw)
        r.raise_for_status()
        return r.json()

    def _post(self, url, json_body=None, headers=None):
        import requests
        h = {"User-Agent": "Mozilla/5.0 (stock-agent/1.0)"}
        if headers:
            h.update(headers)
        kw = dict(timeout=self.timeout, headers=h)
        if self.proxy:
            kw["proxies"] = {"http": self.proxy, "https": self.proxy}
        r = requests.post(url, json=json_body, **kw)
        r.raise_for_status()
        return r.json()


def create_adapter(source_code, **kwargs):
    """工厂：按 source_code 创建 adapter"""
    if source_code == "kalshi":
        from data.collectors.prediction.kalshi import KalshiAdapter
        return KalshiAdapter(**kwargs)
    if source_code == "polymarket":
        from data.collectors.prediction.polymarket import PolymarketAdapter
        return PolymarketAdapter(**kwargs)
    raise ValueError(f"未知预测源: {source_code}")
