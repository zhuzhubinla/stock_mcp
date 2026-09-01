"""Prediction Collector：多源拉取 → 归一化 → 落库（设计文档 8.3 统一流程）

流程：Source API → Adapter → Normalization → Market/Event Mapping → 落库
      → Consensus（多源加权）→ Momentum（24h/7d）→ Signal（映射后）
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.collectors.prediction.base import create_adapter
from data.repositories import prediction_repo as repo
from data.repositories.mysql_db import get_conn

# 源 → 适配器配置
SOURCE_CONFIG = {
    "kalshi": {"base_url": "https://demo-api.kalshi.co/trade-api/v2"},
    "polymarket": {"base_url": "https://gamma-api.polymarket.com"},
    "metaculus": {"base_url": "https://www.metaculus.com/api2"},
}


def collect_source(source_code, limit=20, persist=True, proxy=None):
    """拉取单个源的市场/事件并落库"""
    src = repo.get_source(source_code)
    if not src or not src["enabled"]:
        return {"source": source_code, "status": "disabled"}
    cfg = dict(SOURCE_CONFIG.get(source_code, {}))
    if proxy:
        cfg["proxy"] = proxy
    adapter = create_adapter(source_code, **cfg)
    stats = {"source": source_code, "events": 0, "markets": 0, "probabilities": 0}

    try:
        # 1. 拉事件
        events = adapter.fetch_events(limit=limit)
        for ev in events:
            if _is_sports_shard(ev.get("title") or ""):
                continue
            event_id = None
            if ev.get("title"):
                event_id = repo.upsert_event(
                    ev["external_id"], ev["title"], ev.get("category"),
                    ev.get("start_time"), ev.get("end_time"), ev.get("status", "open"))
                stats["events"] += 1
            # 2. 事件关联市场（Kalshi /events/{id} 返回 markets[]，多市场事件的关键）
            if event_id and ev.get("external_id"):
                try:
                    if hasattr(adapter, "fetch_event_markets"):
                        detail_markets = adapter.fetch_event_markets(ev["external_id"])
                        for dm in detail_markets:
                            if dm and dm.get("external_id"):
                                _persist_market(repo, src, event_id, dm, adapter, stats)
                    else:
                        detail = adapter.fetch_market_detail(ev["external_id"])
                        if detail and detail.get("external_id"):
                            _persist_market(repo, src, event_id, detail, adapter, stats)
                except Exception as e:
                    print(f"[prediction] 事件市场关联失败 {ev.get('external_id','')[:30]}: {str(e)[:80]}")
        # 3. 兜底：直接拉市场列表（跳过体育 shard）
        try:
            markets = adapter.fetch_markets(limit=limit, status="open")
            for m in markets:
                if _is_sports_shard(m.get("title") or ""):
                    continue
                event_id = _find_or_create_event(repo, m)
                if event_id:
                    _persist_market(repo, src, event_id, m, adapter, stats)
        except Exception as e:
            print(f"[prediction] {source_code} 市场列表失败: {str(e)[:100]}")
    except Exception as e:
        print(f"[prediction] {source_code} 拉取失败: {str(e)[:150]}")
        return {"source": source_code, "status": "error", "error": str(e)}

    return {"source": source_code, "status": "ok", **stats}


def _is_sports_shard(title):
    """过滤 Kalshi 体育跨类 shard：'yes X,yes Y' 组合市场（无股票意义）"""
    t = title.strip().lower()
    if t.startswith("yes ") and ",yes " in t:
        return True
    # 纯体育关键词
    sports_kw = ("game", "match", "vs ", "nba", "nfl", "mlb", "nhl", "soccer",
                 "tennis", "football", "basketball", "baseball", "hockey",
                 "championship", "race", "goal", "tournament")
    return any(k in t for k in sports_kw)


def _persist_market(repo, src, event_id, m, adapter, stats):
    """归一化市场 → 落库 + 保存概率历史 + outcome"""
    if not m.get("external_id"):
        return
    mid = repo.upsert_market(
        event_id, src["id"], m["external_id"], m.get("title"),
        market_type=m.get("market_type", "binary"),
        status=m.get("status", "active"),
        yes_ask=m.get("yes_ask"), yes_bid=m.get("yes_bid"),
        last_price=m.get("last_price"),
        volume=m.get("volume"), open_interest=m.get("open_interest"),
        liquidity=m.get("liquidity"), close_time=m.get("close_time"),
        detail=m.get("detail"))
    if mid:
        stats["markets"] += 1
    # outcome：binary → yes/no；有 last_price 存 yes
    last = m.get("last_price")
    if last is not None and mid:
        repo.upsert_outcome(mid, "yes", "Yes", last)
        repo.upsert_outcome(mid, "no", "No", round(1 - last, 4))
        repo.save_probability(mid, "yes", last)
        stats["probabilities"] += 1


def _find_or_create_event(repo, m):
    """市场无事件时按标题归并创建事件"""
    title = m.get("title") or m.get("event_external_id") or "unknown"
    ev = repo.get_event(title=title)
    if ev:
        return ev["id"]
    return repo.upsert_event(m.get("event_external_id") or title, title,
                             _category_of(m), None, m.get("close_time"), "open")


def _category_of(m):
    detail = m.get("detail") or {}
    t = ((m.get("title") or "") + " " + str(detail.get("category") or "")).lower()
    for cat, kws in {
        "macro": ["fed", "cpi", "inflation", "rate", "gdp", "recession", "unemployment"],
        "election": ["president", "election", "senate", "vote"],
        "company": ["earnings", "ipo", "stock", "acquisition", "revenue"],
        "crypto": ["bitcoin", "btc", "eth", "crypto"],
        "ai": ["ai", "openai", "nvidia", "chips", "semiconductor"],
        "geopolitics": ["war", "nato", "israel", "russia", "china"],
    }.items():
        if any(k in t for k in kws):
            return cat
    return "other"


def collect_all(limit=20, proxy=None, sources=None):
    """采集所有启用源"""
    srcs = repo.list_sources(enabled_only=True)
    results = []
    for s in srcs:
        if sources and s["code"] not in sources:
            continue
        results.append(collect_source(s["code"], limit=limit, proxy=proxy))
    return {"results": results, "count": len(results)}


if __name__ == "__main__":
    import json
    print(json.dumps(collect_all(limit=10), ensure_ascii=False, indent=1, default=str))
