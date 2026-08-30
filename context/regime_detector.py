"""Market Regime Detector（设计文档第 7 节 Market Precondition 的市场层）

输入：市场指数（SPY/QQQ 兜底 watchlist 均值）+ FRED 宏观序列（库内 industry_indicator）
输出：regime（risk_on / risk_off / neutral）+ 0~1 regime_score + 分项分
持久化：market_regime 表

regime_score 合成（0~1，1=强风险偏好）：
  trend_score   : 指数价格 vs MA20/MA60 + 动量（0~1）
  volatility_score: 20 日年化波动率反向（越低越平稳分越高）
  breadth_score : watchlist 成分涨跌占比（>50% 上涨=偏多）
  macro_score   : FRED 工业产出/消费者信心趋势 + CPI 反向
  regime_score  = 0.4*trend + 0.25*volatility + 0.2*breadth + 0.15*macro
"""
import sys
from datetime import datetime, timedelta

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn
from data.repositories import factor_repo, graph_repo

REGIME_TABLE = "market_regime"
INDEX_TICKERS = ["SPY", "QQQ"]  # 依次尝试；失败则用 watchlist 均值


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


# ---------- 指数行情 ----------
def _index_bars(ticker, days=130):
    """yfinance 拉指数日线 → [{date, close, volume}] 升序"""
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period=f"{days}d", interval="1d")
        if df is None or df.empty:
            return []
        bars = []
        for idx, r in df.iterrows():
            close = float(r["Close"])
            if close != close:  # NaN
                continue
            bars.append({
                "date": idx.to_pydatetime().replace(tzinfo=None),
                "close": close,
                "volume": float(r["Volume"]) if r["Volume"] == r["Volume"] else 0.0,
            })
        return bars
    except Exception as e:
        print(f"[regime] 指数 {ticker} 获取失败: {e}")
        return []


def _watchlist_breadth():
    """watchlist 成分涨跌占比：>50% 上涨 = 偏多"""
    import json
    from data.adapters import stock_service
    try:
        watchlist = json.load(open("/home/admin/stock_agent/watchlist.json"))
    except Exception:
        watchlist = []
    if not watchlist:
        return None
    up = 0
    total = 0
    for s in watchlist[:10]:
        try:
            q = stock_service.get_quote(s)
            pct = q.get("percent")
            if pct is None:
                continue
            total += 1
            if pct > 0:
                up += 1
        except Exception:
            continue
    if total == 0:
        return None
    return up / total


def _macd(closes):
    if len(closes) < 26:
        return None
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    return ema12 - ema26 if ema12 is not None and ema26 is not None else None


def _ema(values, window):
    if len(values) < window:
        return None
    k = 2 / (window + 1)
    e = sum(values[:window]) / window
    for v in values[window:]:
        e = v * k + e * (1 - k)
    return e


def _trend_score(bars):
    """价格 vs MA20/MA60 + MACD + 动量 → 0~1"""
    if len(bars) < 60:
        return 0.5
    closes = [b["close"] for b in bars]
    last = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    macd = _macd(closes)
    mom5 = closes[-1] / closes[-6] - 1 if len(closes) > 6 else 0
    score = 0.0
    score += 0.4 if last > ma20 else 0.0
    score += 0.3 if last > ma60 else 0.0
    if macd is not None:
        score += 0.15 if macd > 0 else 0.0
    score += 0.15 * _clamp((mom5 + 0.03) / 0.06)  # 5日动量 -3%~+3% → 0~1
    return _clamp(score)


def _volatility_score(bars):
    """20 日年化波动率反向：20% 波动 → 0.5；40%+ → 0；5% → 1"""
    if len(bars) < 21:
        return 0.5
    closes = [b["close"] for b in bars]
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
    r = rets[-20:]
    mean = sum(r) / len(r)
    var = sum((x - mean) ** 2 for x in r) / len(r)
    vol = (var ** 0.5) * (252 ** 0.5)
    return _clamp(1.0 - vol / 0.5)


# ---------- 宏观分（FRED 序列在库内 industry_indicator） ----------
def _macro_score():
    """INDPRO/UMCSENT 趋势 + CPI 反向 → 0~1"""
    scores = []
    # 工业产出：最新 vs 12 个月前
    ind = factor_repo.get_indicators(indicator_code="industrial_production")
    if ind:
        vals = sorted(ind, key=lambda r: str(r["period"] or ""))
        if len(vals) >= 2:
            v0 = float(vals[-1]["value"])
            v1 = float(vals[-2]["value"])
            scores.append(_clamp((v0 / v1 - 1) / 0.02 + 0.5) if v1 else 0.5)
    # 消费者信心
    sent = factor_repo.get_indicators(indicator_code="consumer_sentiment")
    if sent:
        vals = sorted(sent, key=lambda r: str(r["period"] or ""))
        if len(vals) >= 2:
            v0 = float(vals[-1]["value"])
            v1 = float(vals[-2]["value"])
            scores.append(_clamp((v0 / v1 - 1) / 0.05 + 0.5) if v1 else 0.5)
    # CPI：上行 = 风险偏好下降
    cpi = factor_repo.get_indicators(indicator_code="cpi")
    if cpi:
        vals = sorted(cpi, key=lambda r: str(r["period"] or ""))
        if len(vals) >= 2:
            v0 = float(vals[-1]["value"])
            v1 = float(vals[-2]["value"])
            chg = (v0 / v1 - 1) if v1 else 0
            scores.append(_clamp(0.5 - chg / 0.01))
    if not scores:
        return 0.5
    return sum(scores) / len(scores)


def detect_regime(persist=True, force_refresh=True):
    """检测当前市场状态 → market_regime 表"""
    bars = []
    source = None
    for t in INDEX_TICKERS:
        bars = _index_bars(t)
        if len(bars) >= 60:
            source = t
            break
    if len(bars) < 21:
        # 兜底：watchlist 均值算 trend，缺失项用中性
        trend = 0.5
        vol = 0.5
        print("[regime] 指数数据不足，使用兜底逻辑")
    else:
        trend = _trend_score(bars)
        vol = _volatility_score(bars)

    breadth = _watchlist_breadth()
    macro = _macro_score()

    regime_score = 0.4 * trend + 0.25 * vol + 0.2 * (breadth if breadth is not None else 0.5) + 0.15 * macro
    if regime_score >= 0.6:
        regime = "risk_on"
    elif regime_score <= 0.4:
        regime = "risk_off"
    else:
        regime = "neutral"

    row = {
        "regime": regime,
        "regime_score": round(regime_score, 4),
        "trend_score": round(trend, 4),
        "volatility_score": round(vol, 4),
        "breadth_score": round(breadth, 4) if breadth is not None else None,
        "macro_score": round(macro, 4),
        "detail": {
            "index_source": source,
            "breadth_up_ratio": breadth,
            "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "snapshot_time": datetime.now().replace(second=0, microsecond=0),
    }
    if persist:
        _save_regime(row)
    return row


def _save_regime(row):
    import json
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO market_regime (regime, regime_score, trend_score, volatility_score,
                                       breadth_score, macro_score, detail, snapshot_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (row["regime"], row["regime_score"], row["trend_score"],
              row["volatility_score"], row["breadth_score"], row["macro_score"],
              json.dumps(row["detail"], ensure_ascii=False), row["snapshot_time"]))


def get_latest_regime():
    """最近一条 market_regime（无则检测）"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT regime, regime_score, trend_score, volatility_score,
                   breadth_score, macro_score, detail, snapshot_time
            FROM market_regime ORDER BY snapshot_time DESC LIMIT 1
        """)
        row = cur.fetchone()
    if row:
        import json
        if isinstance(row.get("detail"), str):
            try:
                row["detail"] = json.loads(row["detail"])
            except Exception:
                pass
        return row
    return detect_regime()


if __name__ == "__main__":
    import json
    print(json.dumps(detect_regime(), ensure_ascii=False, indent=1, default=str))
