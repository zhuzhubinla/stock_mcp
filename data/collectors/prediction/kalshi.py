"""Kalshi Adapter（设计文档 8.3，P0 源）

真实 API：https://api.elections.kalshi.com/trade-api/v2（生产，需账号）
沙盒 API：https://demo-api.kalshi.co/trade-api/v2（无需 key，大陆可直连，2026-08-30 实测通）

字段说明（Kalshi v2）：
  market: last_price_dollars / yes_bid_dollars / yes_ask_dollars /
          open_interest_fp / liquidity_dollars / floor_strike / cap_strike / status
  概率 = last_price_dollars（0~1，二进制 YES 价）

默认走 demo 端点（无 key 可用）；配置 api_key + 生产 base_url 即切生产。
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.collectors.prediction.base import PredictionAdapter

DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"
PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiAdapter(PredictionAdapter):

    source_code = "kalshi"

    def __init__(self, base_url=None, api_key=None, timeout=15, proxy=None):
        super().__init__(base_url=base_url or DEMO_BASE, api_key=api_key,
                         timeout=timeout, proxy=proxy)
        self.headers = {"User-Agent": "Mozilla/5.0 (stock-agent/1.0)"}
        if self.api_key:
            self.headers["Kalshi-Api-Key"] = self.api_key

    # ---------- 拉取 ----------
    def fetch_events(self, limit=20, status="open"):
        """事件列表 → 归一化"""
        d = self._get(f"{self.base_url}/events",
                      params={"limit": limit, "status": status},
                      headers=self.headers)
        out = []
        for e in d.get("events", []):
            out.append(self._norm_event(e))
        return out

    def fetch_markets(self, limit=20, status="open", series_ticker=None):
        """市场列表（含价格）"""
        params = {"limit": limit, "status": status}
        if series_ticker:
            params["series_ticker"] = series_ticker
        d = self._get(f"{self.base_url}/markets", params=params,
                      headers=self.headers)
        return [self._norm_market(m) for m in d.get("markets", [])]

    def fetch_market_detail(self, external_id):
        d = self._get(f"{self.base_url}/markets/{external_id}",
                      headers=self.headers)
        m = d.get("market", {})
        return self._norm_market(m)

    def fetch_event_markets(self, event_external_id):
        """事件详情端点 /events/{id} → {event, markets[]}（多市场事件的关键路径）"""
        d = self._get(f"{self.base_url}/events/{event_external_id}",
                      headers=self.headers)
        return [self._norm_market(m) for m in d.get("markets", [])]

    def fetch_orderbook(self, external_id):
        """订单簿（可用性验证用）"""
        d = self._get(f"{self.base_url}/markets/{external_id}/orderbook",
                      headers=self.headers)
        return d.get("orderbook_fp", {})

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
            "external_id": e.get("event_ticker") or e.get("ticker"),
            "title": e.get("title"),
            "category": _guess_category(e.get("title") or ""),
            "start_time": _dt(e.get("open_time")),
            "end_time": _dt(e.get("close_time") or e.get("expiration_time")),
            # Kalshi events 列表不带 status 字段（None）→ 能拉到即视为 open
            "status": "open" if e.get("status") in (None, "open", "active", "unopened") else "closed",
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
        # Kalshi 沙盒用 *_dollars 后缀；生产版本同样有
        def _num(*keys):
            for k in keys:
                v = m.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None
            return None
        return {
            "external_id": m.get("ticker"),
            "event_external_id": m.get("event_ticker"),
            "title": m.get("title"),
            "market_type": _market_type(m),
            "status": "active" if m.get("status") in ("active", "open") else "closed",
            "yes_ask": _num("yes_ask_dollars", "yes_ask"),
            "yes_bid": _num("yes_bid_dollars", "yes_bid"),
            "last_price": _num("last_price_dollars", "last_price"),
            "volume": _num("volume", "volume_fp"),
            "open_interest": _num("open_interest_fp", "open_interest"),
            "liquidity": _num("liquidity_dollars"),
            "close_time": _dt(m.get("close_time") or m.get("expiration_time")),
            "detail": {k: m.get(k) for k in
                       ("floor_strike", "cap_strike", "strike_type", "market_type",
                        "expiration_value", "can_close_early", "result")},
            "raw": m,
        }


def _market_type(m):
    if m.get("cap_strike") is not None or m.get("floor_strike") is not None:
        return "range"
    if m.get("strike_type"):
        return "strike"
    title = (m.get("title") or "").lower()
    if "between" in title:
        return "range"
    return "binary"


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
    a = KalshiAdapter()
    evs = a.fetch_events(limit=5)
    print(f"events: {len(evs)}")
    for e in evs[:5]:
        print(f"  {e['external_id'][:40]} | {e['title'][:45]} | {e['category']}")
    ms = a.fetch_markets(limit=5, status="open")
    print(f"markets: {len(ms)}")
    for m in ms[:5]:
        print(f"  {m['external_id'][:40]} | {(m['title'] or '')[:30]} | last={m['last_price']}")
