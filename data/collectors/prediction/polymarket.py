"""Polymarket Adapter（设计文档 8.3，P0 源）

API：
  Gamma: https://gamma-api.polymarket.com/markets（事件/市场元数据，公开无 key）
  CLOB:  https://clob.polymarket.com（订单簿/价格，公开无 key）

大陆直连不可达（2026-08-30 实测超时）→ 设计文档 21 节 Option B：
  海外 VPS 跑 collector，HTTPS 同步标准化数据回国内；或本机配置 HTTP(S) 代理。

概率 = outcomePrices（Gamma markets 返回如 ["0.53","0.47"]，对应 outcomes ["Yes","No"]）
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.collectors.prediction.base import PredictionAdapter

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


class PolymarketAdapter(PredictionAdapter):

    source_code = "polymarket"

    def __init__(self, base_url=None, api_key=None, timeout=20, proxy=None):
        super().__init__(base_url=base_url or GAMMA_BASE, api_key=api_key,
                         timeout=timeout, proxy=proxy)
        self.clob_url = CLOB_BASE

    # ---------- 拉取 ----------
    def fetch_events(self, limit=20, status="open"):
        """Gamma 事件列表（tag/系列）"""
        params = {"limit": limit, "active": "true" if status == "open" else "false",
                  "closed": "false" if status == "open" else "true"}
        d = self._get(f"{self.base_url}/events", params=params)
        out = []
        for e in (d if isinstance(d, list) else []):
            out.append(self._norm_event(e))
        return out

    def fetch_markets(self, limit=20, status="open"):
        """Gamma 市场列表（含 outcomePrices）"""
        params = {"limit": limit,
                  "active": "true" if status == "open" else "false",
                  "closed": "false" if status == "open" else "true"}
        d = self._get(f"{self.base_url}/markets", params=params)
        return [self._norm_market(m) for m in (d if isinstance(d, list) else [])]

    def fetch_market_detail(self, external_id):
        d = self._get(f"{self.base_url}/markets/{external_id}")
        return self._norm_market(d) if isinstance(d, dict) else {}

    def fetch_orderbook(self, external_id):
        """CLOB 订单簿（token_id 查询）"""
        try:
            d = self._get(f"{self.clob_url}/book", params={"token_id": external_id})
            return d
        except Exception:
            return {}

    def fetch_probability_history(self, external_id, hours=24):
        """Gamma price-history（CLOB 端点，token_id）"""
        try:
            d = self._get(f"{self.clob_url}/prices-history",
                          params={"market": external_id,
                                  "interval": "1h",
                                  "start_time": int(datetime.now().timestamp() - hours * 3600),
                                  "end_time": int(datetime.now().timestamp())})
            return d.get("history", [])
        except Exception:
            return []

    # ---------- 归一化 ----------
    @staticmethod
    def _norm_event(e):
        def _dt(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                return None
        return {
            "external_id": e.get("id") or e.get("slug"),
            "title": e.get("title"),
            "category": _guess_category(e.get("title") or ""),
            "start_time": _dt(e.get("startDate")),
            "end_time": _dt(e.get("endDate")),
            "status": "open" if e.get("active") else "closed",
            "raw": e,
        }

    @staticmethod
    def _norm_market(m):
        def _dt(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                return None
        outcomes = m.get("outcomes") or []
        prices = m.get("outcomePrices") or []
        last_price = None
        yes_ask = yes_bid = None
        if prices:
            try:
                last_price = float(prices[0]) if prices[0] is not None else None
            except (TypeError, ValueError):
                last_price = None
        return {
            "external_id": m.get("id") or m.get("conditionId"),
            "event_external_id": m.get("events")[0]["id"] if m.get("events") else m.get("event_id"),
            "title": m.get("question"),
            "market_type": "multi" if len(outcomes) > 2 else "binary",
            "status": "active" if m.get("active") and not m.get("closed") else "closed",
            "yes_ask": yes_ask,
            "yes_bid": yes_bid,
            "last_price": last_price,
            "volume": _num(m.get("volume")),
            "open_interest": _num(m.get("openInterest")),
            "liquidity": _num(m.get("liquidity")),
            "close_time": _dt(m.get("endDate")),
            "detail": {"outcomes": outcomes, "outcomePrices": prices,
                       "conditionId": m.get("conditionId"),
                       "slug": m.get("slug")},
            "raw": m,
        }


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _guess_category(title):
    t = title.lower()
    cats = {
        "macro": ["fed", "cpi", "inflation", "rate", "gdp", "recession", "unemployment",
                  "treasury", "yield", "oil", "crude"],
        "election": ["president", "election", "senate", "congress", "vote", "primary"],
        "company": ["earnings", "ipo", "stock", "acquisition", "merger", "ceo", "revenue"],
        "crypto": ["bitcoin", "btc", "eth", "ethereum", "crypto"],
        "ai": ["ai", "openai", "chatgpt", "nvidia", "chips", "semiconductor"],
        "geopolitics": ["war", "ceasefire", "nato", "israel", "russia", "china", "iran"],
        "sports": ["game", "match", "nba", "nfl", "mlb", "soccer", "tennis", "championship"],
    }
    for cat, kws in cats.items():
        if any(k in t for k in kws):
            return cat
    return "other"


if __name__ == "__main__":
    import json
    a = PolymarketAdapter()
    try:
        ms = a.fetch_markets(limit=5)
        print(f"markets: {len(ms)}")
        for m in ms[:5]:
            print(f"  {m['external_id'][:30]} | {(m['title'] or '')[:40]} | last={m['last_price']}")
    except Exception as e:
        print(f"Polymarket 直连失败（大陆网络预期内）: {str(e)[:80]}")
        print("海外 VPS 部署模式：见 docs/PREDICTION.md")
