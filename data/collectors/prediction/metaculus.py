"""Metaculus Adapter（设计文档 8.3，P1 源）

API v2：https://www.metaculus.com/api2（2026-09 起强制鉴权，需 API token）
  token 获取：https://www.metaculus.com/settings/account/（登录后生成）
  鉴权头：Authorization: Token <token>（Django REST Framework TokenAuthentication）

模式说明：Metaculus 没有独立"市场"，每个 question 即事件+市场。
  - binary question（possibilities.type=binary）：概率 = community_prediction.full.q2（社区中位数）
  - multiple_choice question：market_type=multi，各选项概率在 detail 中保留
  无订单簿 → yes_ask/yes_bid/volume/open_interest/liquidity 置空；
  number_of_predictions/weight 存入 detail（可作为流动性/热度代理）。

token 注入：环境变量 METACULUS_API_KEY（config.py 读取），缺省时拉取直接报错。
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.collectors.prediction.base import PredictionAdapter

METACULUS_BASE = "https://www.metaculus.com/api2"


class MetaculusAdapter(PredictionAdapter):

    source_code = "metaculus"

    def __init__(self, base_url=None, api_key=None, timeout=20, proxy=None):
        if api_key is None:
            try:
                from config import METACULUS_API_KEY
                api_key = METACULUS_API_KEY
            except ImportError:
                api_key = ""
        super().__init__(base_url=base_url or METACULUS_BASE, api_key=api_key,
                         timeout=timeout, proxy=proxy)
        self.headers = {}
        if self.api_key:
            self.headers["Authorization"] = f"Token {self.api_key}"

    # ---------- 拉取 ----------
    def _questions(self, limit=20, status="open", question_type="forecast"):
        """通用 questions 列表请求（Metaculus 无分页时按 limit 截断）"""
        if not self.api_key:
            raise RuntimeError(
                "Metaculus API 需要 token：设置环境变量 METACULUS_API_KEY "
                "（在 https://www.metaculus.com/settings/account/ 生成）")
        params = {"limit": limit, "order_by": "-activity",
                  "type": question_type}
        if status == "open":
            params["status"] = "open"
        d = self._get(f"{self.base_url}/questions/", params=params,
                      headers=self.headers)
        return d.get("results", []) if isinstance(d, dict) else []

    def fetch_events(self, limit=20, status="open"):
        """question 列表 → 事件列表（binary + multiple_choice）"""
        out = []
        for q in self._questions(limit=limit, status=status, question_type="forecast"):
            if self._is_binary(q) or self._is_multi(q):
                out.append(self._norm_event(q))
        return out

    def fetch_markets(self, limit=20, status="open"):
        """question 列表 → 市场列表（含社区概率）"""
        out = []
        for q in self._questions(limit=limit, status=status, question_type="forecast"):
            if self._is_binary(q) or self._is_multi(q):
                out.append(self._norm_market(q))
        return out

    def fetch_market_detail(self, external_id):
        d = self._get(f"{self.base_url}/questions/{external_id}/",
                      headers=self.headers)
        return self._norm_market(d) if isinstance(d, dict) else {}

    def fetch_event_markets(self, event_external_id):
        """question 自身即市场：直接返回该 question 的归一化市场"""
        d = self._get(f"{self.base_url}/questions/{event_external_id}/",
                      headers=self.headers)
        if not isinstance(d, dict):
            return []
        return [self._norm_market(d)]

    def fetch_probability_history(self, external_id, hours=24):
        """社区概率时序：Metaculus 无公开免鉴权时序端点 → 快照法（每次 sync 落库累积 momentum）"""
        return []

    # ---------- 归一化 ----------
    @staticmethod
    def _is_binary(q):
        return (q.get("possibilities") or {}).get("type") == "binary"

    @staticmethod
    def _is_multi(q):
        return (q.get("possibilities") or {}).get("type") == "multiple_choice"

    @staticmethod
    def _norm_event(q):
        def _dt(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                return None
        return {
            "external_id": str(q.get("id")),
            "title": q.get("title"),
            "category": _guess_category(q.get("title") or ""),
            "start_time": _dt(q.get("created_time")),
            "end_time": _dt(q.get("close_time") or q.get("resolve_time")),
            "status": {"open": "open", "closed": "closed", "resolved": "settled"}.get(q.get("status"), "open"),
            "raw": q,
        }

    @staticmethod
    def _norm_market(q):
        def _dt(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                return None
        cp = q.get("community_prediction") or {}
        full = cp.get("full") or {}
        last_price = None
        for k in ("q2", "mean"):
            v = full.get(k)
            if v is not None:
                try:
                    last_price = float(v)
                    break
                except (TypeError, ValueError):
                    pass
        if last_price is not None:
            last_price = round(min(max(last_price, 0.0), 1.0), 4)
        poss = q.get("possibilities") or {}
        return {
            "external_id": str(q.get("id")),
            "event_external_id": str(q.get("id")),
            "title": q.get("title"),
            "market_type": "multi" if (poss.get("type") == "multiple_choice") else "binary",
            "status": {"open": "active", "closed": "closed", "resolved": "settled"}.get(q.get("status"), "active"),
            "yes_ask": None,
            "yes_bid": None,
            "last_price": last_price,
            "volume": None,
            "open_interest": None,
            "liquidity": None,
            "close_time": _dt(q.get("close_time") or q.get("resolve_time")),
            "detail": {"possibilities": poss, "community_prediction": cp,
                       "number_of_predictions": q.get("number_of_predictions"),
                       "weight": q.get("weight"), "url": q.get("url")},
            "raw": q,
        }


def _guess_category(title):
    t = title.lower()
    cats = {
        "macro": ["fed", "cpi", "inflation", "rate", "gdp", "recession", "unemployment",
                  "treasury", "yield", "oil", "crude", "interest"],
        "election": ["president", "election", "senate", "congress", "vote", "primary",
                     "democrat", "republican"],
        "company": ["earnings", "ipo", "stock", "acquisition", "merger", "ceo",
                    "revenue", "tesla", "apple", "microsoft", "google", "amazon"],
        "crypto": ["bitcoin", "btc", "eth", "ethereum", "crypto"],
        "ai": ["ai", "openai", "chatgpt", "gpt-", "nvidia", "chips", "semiconductor",
               "artificial intelligence", "llm", "agi"],
        "geopolitics": ["war", "ceasefire", "nato", "israel", "russia", "china",
                        "iran", "ukraine", "taiwan"],
        "space": ["spacex", "nasa", "rocket", "orbit", "moon", "mars", "satellite"],
        "climate": ["climate", "temperature", "emission", "co2", "renewable"],
        "science": ["vaccine", "cancer", "drug", "clinical trial", "fda"],
    }
    for cat, kws in cats.items():
        if any(k in t for k in kws):
            return cat
    return "other"


if __name__ == "__main__":
    import json
    a = MetaculusAdapter()
    try:
        ms = a.fetch_markets(limit=5)
        print(f"markets: {len(ms)}")
        for m in ms[:5]:
            print(f"  {m['external_id']} | {(m['title'] or '')[:50]} | last={m['last_price']} | {m['market_type']}")
    except Exception as e:
        print(f"Metaculus 拉取失败: {type(e).__name__}: {str(e)[:120]}")
