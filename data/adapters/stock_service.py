"""Stock Service：数据获取 + MySQL 缓存 + 分析汇总"""
import sys
from datetime import datetime, timedelta, timezone
sys.path.append("/home/admin/stock_agent")

import re
import requests
import finnhub
import yfinance as yf

from config import FINNHUB_API_KEY, QUOTE_TTL, HISTORY_TTL, NEWS_TTL, FUNDAMENTAL_TTL
from data.repositories import mysql_db as db
from analytics import trend, scoring

finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

_NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
}


def _nasdaq_history(symbol, days=120):
    """Nasdaq 官方 API 兜底：免费、无需 key、返回真实日线 OHLCV"""
    from datetime import datetime, timedelta
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")
    url = (f"https://api.nasdaq.com/api/quote/{symbol}/historical"
           f"?assetclass=stocks&fromdate={from_date}&todate={to_date}&limit={days}")
    r = requests.get(url, headers=_NASDAQ_HEADERS, timeout=20)
    r.raise_for_status()
    rows = r.json().get("data", {}).get("tradesTable", {}).get("rows", [])
    if not rows:
        return []

    def _num(v):
        if v in (None, "", "N/A"):
            return None
        return float(str(v).replace("$", "").replace(",", ""))

    bars = []
    for row in rows:
        try:
            ts = datetime.strptime(row["date"], "%m/%d/%Y")
        except ValueError:
            continue
        close = _num(row.get("close"))
        if close is None:
            continue
        bars.append({
            "timestamp": ts,
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "close": close,
            "volume": int(_num(row.get("volume")) or 0),
            "source": "nasdaq",
        })
    return bars


# ---------- 行情 ----------
def get_quote(symbol, force_refresh=False):
    """获取实时行情，优先 Finnhub 实时，失败才用 MySQL 缓存"""
    try:
        data = finnhub_client.quote(symbol)
        quote = {
            "symbol": symbol,
            "price": data.get("c"),
            "change": data.get("d"),
            "percent": data.get("dp"),
            "high": data.get("h"),
            "low": data.get("l"),
            "open": data.get("o"),
            "prev_close": data.get("pc"),
            "time": datetime.fromtimestamp(data.get("t", 0), tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
            "source": "finnhub",
        }
        # 写缓存（不覆盖已有 volume）
        if quote["price"] and quote["time"]:
            db.upsert_price(symbol, datetime.now().replace(second=0, microsecond=0),
                            quote["open"], quote["high"], quote["low"],
                            quote["price"], None, source="finnhub")
        return quote
    except Exception as e:
        if not force_refresh and db.price_fresh(symbol, QUOTE_TTL):
            row = db.get_latest_price(symbol)
            return {
                "symbol": symbol,
                "price": float(row["close"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "prev_close": None,
                "change": None,
                "percent": None,
                "time": row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                "source": "mysql_cache",
            }
        return {"symbol": symbol, "price": None, "error": str(e)}


# ---------- 历史行情 ----------
def get_history(symbol, days=90, force_refresh=False):
    """获取历史 OHLCV，优先 MySQL 缓存，不足则拉 yfinance"""
    rows = db.get_prices(symbol, days)
    # 缓存够新鲜且条数足够才直接用，否则刷新（避免只有 1 条 quote 时短路）
    if (not force_refresh and rows and len(rows) >= 10
            and (datetime.now() - rows[-1]["timestamp"]).total_seconds() < HISTORY_TTL):
        return _rows_to_history(rows)

    # 1) yfinance
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period=f"{days}d", interval="1d")
        if df is not None and not df.empty:
            for idx, r in df.iterrows():
                ts = idx.to_pydatetime().replace(tzinfo=None)
                db.upsert_price(symbol, ts,
                                float(r["Open"]), float(r["High"]),
                                float(r["Low"]), float(r["Close"]),
                                int(r["Volume"]) if r["Volume"] == r["Volume"] else None,
                                source="yfinance")
            rows = db.get_prices(symbol, days)
            if len(rows) > 1:
                return _rows_to_history(rows)
    except Exception:
        pass
    # 2) finnhub 蜡烛
    try:
        end = int(datetime.now().timestamp())
        start = int((datetime.now() - timedelta(days=days)).timestamp())
        candles = finnhub_client.stock_candles(symbol, "D", start, end)
        if candles and candles.get("s") == "ok":
            for i in range(len(candles["t"])):
                ts = datetime.fromtimestamp(candles["t"][i], tz=timezone.utc).replace(tzinfo=None)
                db.upsert_price(symbol, ts, candles["o"][i], candles["h"][i],
                                candles["l"][i], candles["c"][i], candles["v"][i], source="finnhub")
            rows = db.get_prices(symbol, days)
            if len(rows) > 1:
                return _rows_to_history(rows)
    except Exception:
        pass
    # 3) Nasdaq 官方 API 兜底
    try:
        bars = _nasdaq_history(symbol, days)
        if len(bars) > 1:
            for b in bars:
                db.upsert_price(symbol, b["timestamp"], b["open"], b["high"],
                                b["low"], b["close"], b["volume"], source=b["source"])
            rows = db.get_prices(symbol, days)
            if len(rows) > 1:
                return _rows_to_history(rows)
    except Exception:
        pass
    return {"symbol": symbol, "error": "历史数据获取失败", "bars": []}


def _rows_to_history(rows):
    # 按日期去重：quote 当日行（volume 为空）与日线行同日期时，保留 volume 更大的日线行
    by_date = {}
    for r in rows:
        d = r["timestamp"].strftime("%Y-%m-%d")
        cur = by_date.get(d)
        v = int(r["volume"]) if r["volume"] is not None else 0
        if cur is None or v > cur["volume"]:
            by_date[d] = {
                "date": d,
                "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": v,
            }
    # 丢弃最新日期的幻影行（非交易日 quote 写入、volume=0），避免污染量比/指标
    dates = sorted(by_date)
    if len(dates) > 1 and by_date[dates[-1]]["volume"] == 0:
        del by_date[dates[-1]]
    bars = [by_date[d] for d in sorted(by_date)]
    return {"symbol": rows[0]["symbol"] if rows else "", "bars": bars, "count": len(bars)}


# ---------- 新闻（Phase5：stock_news + stock_news_symbol + stock_news_analysis） ----------
def get_news(symbol, limit=5, hours=None, force_refresh=False):
    """获取指定股票近期新闻（含 AI 分析结果），优先 MySQL 缓存，过期自动采集"""
    if not force_refresh and db.news_fresh(symbol, NEWS_TTL):
        rows = db.get_news(symbol, limit, hours)
        if rows:
            return _rows_to_news(symbol, rows)
    try:
        from data.collectors.news.collector import collect
        collect([symbol])
        rows = db.get_news(symbol, limit, hours)
        if rows:
            return _rows_to_news(symbol, rows)
    except Exception as e:
        print(f"[stock_service] get_news 采集失败: {e}")
    rows = db.get_news(symbol, limit, hours)
    return _rows_to_news(symbol, rows) if rows else {"symbol": symbol, "news": [], "count": 0}


def _rows_to_news(symbol, rows):
    news = [{
        "id": r["id"],
        "title": r["title"], "url": r["url"], "source": r["publisher"],
        "published_at": r["published_at"].strftime("%Y-%m-%d %H:%M:%S") if r["published_at"] else None,
        "sentiment": r.get("sentiment"),
        "sentiment_score": float(r["sentiment_score"]) if r.get("sentiment_score") is not None else None,
        "impact_score": float(r["impact_score"]) if r.get("impact_score") is not None else None,
        "relevance_score": float(r["relevance_score"]) if r.get("relevance_score") is not None else None,
        "event_type": r.get("event_type"),
        "content": r.get("content"),
    } for r in rows]
    return {"symbol": symbol, "news": news, "count": len(news)}


def get_news_summary(symbol, hours=24):
    """新闻汇总：数量、总体情绪、高影响事件"""
    rows = db.get_news(symbol, limit=50, hours=hours)
    news = _rows_to_news(symbol, rows)["news"]
    if not news:
        return {"symbol": symbol,
                "hours": hours,
                "total": 0,
                "overall_sentiment": "neutral",
                "avg_sentiment_score": 0.0,
                "high_impact_events": []}
    scores = [n["sentiment_score"] for n in news if n["sentiment_score"] is not None]
    avg = sum(scores) / len(scores) if scores else 0.0
    overall = "positive" if avg > 0.15 else ("negative" if avg < -0.15 else "neutral")
    high_impact = sorted([n for n in news if (n["impact_score"] or 0) >= 0.5],
                         key=lambda n: n["impact_score"], reverse=True)[:5]
    return {"symbol": symbol,
            "hours": hours,
            "total": len(news),
            "overall_sentiment": overall, "avg_sentiment_score": round(avg, 4),
            "high_impact_events": high_impact}


def get_news_sentiment(symbol, hours=24):
    """新闻情绪统计：正/负/中性分布"""
    rows = db.get_news(symbol, limit=100, hours=hours)
    news = _rows_to_news(symbol, rows)["news"]
    dist = {"positive": 0, "negative": 0, "neutral": 0}
    for n in news:
        s = n.get("sentiment") or "neutral"
        dist[s] = dist.get(s, 0) + 1
    return {"symbol": symbol, "hours": hours, "total": len(news), "distribution": dist}


def get_news_impact(symbol, hours=24):
    """高影响新闻列表（按 impact_score 降序）"""
    rows = db.get_news(symbol, limit=100, hours=hours)
    news = sorted(_rows_to_news(symbol, rows)["news"],
                  key=lambda n: n["impact_score"] or 0, reverse=True)
    return {"symbol": symbol, "hours": hours, "top_impact": news[:10]}


def get_news_events(symbol, hours=24, event_type=None):
    """按事件类型聚合的新闻事件（earnings/m_and_a/macro 等）"""
    rows = db.get_events(symbol, hours=hours, event_type=event_type)
    events = []
    for r in rows:
        events.append({
            "id": r["id"], "event_type": r["event_type"], "title": r["title"],
            "description": r["description"],
            "event_time": r["event_time"].strftime("%Y-%m-%d %H:%M:%S") if r["event_time"] else None,
            "impact_score": float(r["impact_score"]) if r["impact_score"] is not None else None,
            "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
        })
    return {"symbol": symbol, "hours": hours, "event_type": event_type,
            "events": events, "count": len(events)}


def get_anomalies(symbol, days=30):
    """价格/成交量异常检测，附窗口内新闻归因"""
    from analytics.anomaly import get_anomalies_with_causes
    return get_anomalies_with_causes(symbol, days=days)


def explain_price_move(symbol, days=10):
    """解释最近一次异常波动（价格异常 + 新闻归因）"""
    from analytics.anomaly import explain_price_move as _explain
    return _explain(symbol, days=days)


# ---------- 基本面 ----------
def _nasdaq_fundamentals(symbol):
    """Nasdaq 官方 API 补充基本面指标"""
    try:
        url = f"https://api.nasdaq.com/api/quote/{symbol}/info?assetclass=stocks"
        r = requests.get(url, headers=_NASDAQ_HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json().get("data", {})
        out = {}
        pd = data.get("primaryData", {}) or {}
        for k, v in pd.items():
            if k in ("lastSalePrice", "netChange", "percentageChange", "volume"):
                out[k] = v
        ks = data.get("keyStats", {}) or {}
        for k, v in ks.items():
            if isinstance(v, dict):
                out[k] = v.get("value")
        # 摘要指标
        summary = data.get("summaryData", {}) or {}
        for k, v in summary.items():
            if isinstance(v, dict):
                out[k] = v.get("value")
        company = data.get("companyData", {}) or {}
        for k, v in company.items():
            if isinstance(v, dict):
                out[k] = v.get("value")
        return out
    except Exception:
        return {}


def get_fundamentals(symbol, force_refresh=False):
    """获取基本面指标（Finnhub + Nasdaq 补充）"""
    rows = db.get_fundamentals(symbol)
    # 关键指标兜底：缓存缺 pe/revenueGrowth 等衍生指标时强制刷新（SEC 同步只写营收/EPS）
    if rows and not force_refresh:
        have = {r["metric"] for r in rows}
        if "pe" not in have and "revenueGrowth" not in have:
            force_refresh = True
    if rows and not force_refresh:
        return {"symbol": symbol, "metrics": [dict(r) for r in rows], "source": "mysql_cache"}
    try:
        data = finnhub_client.company_basic_financials(symbol, "all")
        metric_map = {}
        if data and data.get("metric"):
            metric_map = data["metric"]
        # 常用指标（Finnhub 实际返回带 TTM/Annual 后缀的字段名，映射为规范名）
        finnhub_keys = {
            "pe": ["peTTM", "peBasicExclExtraTTM", "peAnnual"],
            "forwardPE": ["forwardPE"],
            "netMargin": ["netProfitMarginTTM"],
            "grossMargin": ["grossMarginTTM"],
            "roe": ["roeTTM"],
            "roa": ["roaTTM"],
            "revenueGrowth": ["revenueGrowthTTMYoy"],
            "epsGrowth": ["epsGrowthTTMYoy"],
            "debtToEquity": ["totalDebt/totalEquityQuarterly", "longTermDebt/equityQuarterly"],
            "currentRatio": ["currentRatioQuarterly"],
            "dividendYield": ["dividendYieldIndicatedAnnual"],
            "marketCapitalization": ["marketCapitalization"],
            "52WeekHigh": ["52WeekHigh"],
            "52WeekLow": ["52WeekLow"],
            "pb": ["pb"],
        }
        for canonical, src_keys in finnhub_keys.items():
            v = next((metric_map[k] for k in src_keys if metric_map.get(k) is not None), None)
            if v is not None:
                db.upsert_fundamental(symbol, canonical, float(v), period="latest", source="finnhub")

        # Nasdaq 补充
        extra = _nasdaq_fundamentals(symbol)
        nasdaq_map = {
            "Market Cap": "marketCap",
            "P/E Ratio": "pe",
            "EPS": "eps",
            "Dividend Yield": "dividendYield",
            "Beta": "beta",
            "52 Week High": "52WeekHigh",
            "52 Week Low": "52WeekLow",
            "Volume": "volume",
            "Company Name": "companyName",
        }
        for src_k, db_k in nasdaq_map.items():
            v = extra.get(src_k)
            if v is None:
                continue
            try:
                num = float(str(v).replace("$", "").replace("%", "").replace(",", ""))
            except (ValueError, TypeError):
                continue
            db.upsert_fundamental(symbol, db_k, num, period="latest", source="nasdaq")
        rows = db.get_fundamentals(symbol)
        return {"symbol": symbol, "metrics": [dict(r) for r in rows], "source": "finnhub+nasdaq"}
    except Exception as e:
        if rows:
            return {"symbol": symbol, "metrics": [dict(r) for r in rows], "source": "mysql_fallback", "error": str(e)}
        return {"symbol": symbol, "error": str(e), "metrics": []}


# ---------- 技术指标 ----------
def get_technical(symbol, days=120, force_refresh=False):
    hist = get_history(symbol, days=days, force_refresh=force_refresh)
    bars = hist.get("bars", [])
    if not bars:
        return {"symbol": symbol, "error": hist.get("error", "无数据"), "indicators": {}}
    ind = trend.compute_indicators(bars)
    ind["summary"] = trend.summarize_technical(ind)
    return {"symbol": symbol, "indicators": ind}


# ---------- 综合分析 ----------
def analyze(symbol, force_refresh=False):
    """
    汇总行情/历史/新闻/基本面/技术面，跑 Signal Engine，返回结构化结果
    """
    quote = get_quote(symbol, force_refresh)
    print("quote:", quote)
    hist = get_history(symbol, days=120, force_refresh=force_refresh)
    # print("hist:", hist)
    news = get_news(symbol, limit=5, force_refresh=force_refresh)
    print("news:", news)
    fundamentals = get_fundamentals(symbol, force_refresh)
    print("fundamentals:", fundamentals)
    print("fundamentals======")
    ind = trend.compute_indicators(hist.get("bars", [])) if hist.get("bars") else {}
    print("ind:", ind)
    signals = scoring.compute_total(quote, ind, news.get("news", []), fundamentals.get("metrics", []))
    print("signals:", signals)
    result = {
        "symbol": symbol,
        "quote": quote,
        "indicators": ind,
        "news": news.get("news", [])[:5],
        "fundamentals": fundamentals.get("metrics", []),
        "signals": signals,
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    db.save_analysis(symbol, result, analysis_type="general", model="signal-engine-v1")
    return result


if __name__ == "__main__":
    r = analyze("NVDA")
    print(r["symbol"], r["signals"]["total_score"], r["signals"]["level"])
    for c in r["signals"]["components"]:
        print(f"  {c['name']}: {c['score']}  {c['desc']}")
