"""Precondition / Context Engine（设计文档第 7 节）

为每只股票建立 Context Vector（0~1）：
  valuation      估值状态（越高=越贵）
  industry_cycle 行业周期位置（越高=越热/扩张）
  earnings_trend 盈利趋势（越高=加速）
  price_trend    价格趋势（越高=越强）
  expectation    市场预期强度（越高=预期越满）
  macro_regime   宏观状态（越高=越扩张）
  market_regime  Market Precondition（risk_on=1 / risk_off=0）

Context 不是加分项，而是 Signal 的条件变量：
  - 高估值 + 高预期环境下，利好信号打折、利空信号放大
  - 低估值 + 低预期环境下，利好信号放大
持久化：stock_precondition 表（unique: stock_id + computed_at）
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn, get_fundamentals, get_latest_price, get_prices
from data.repositories import graph_repo, factor_repo
from context.regime_detector import get_latest_regime


def _clamp(v, lo=0.0, hi=1.0):
    if v is None:
        return None
    return max(lo, min(hi, float(v)))


# ---------- 分项计算 ----------
def _valuation_state(symbol):
    """PE 相对估值：0~1，越高=越贵。PE<=0 中性 0.5"""
    pe = None
    for f in get_fundamentals(symbol):
        if f["metric"] == "pe" and f["value"]:
            pe = float(f["value"])
            break
    if pe is None or pe <= 0:
        return 0.5
    # PE 0~60 映射到 0~1（PE=15 → 0.25, PE=30 → 0.5, PE=60 → 1）
    return _clamp(pe / 60.0)


def _industry_cycle(symbol):
    """行业周期：公司所属行业的指标最新趋势（产出/价格上行 = 扩张）"""
    comp = graph_repo.get_company(symbol=symbol)
    if not comp:
        return 0.5
    rows = factor_repo.get_indicators(symbol=symbol)
    if not rows:
        return 0.5
    # 取每个指标最新两期算环比，平均后映射
    from collections import defaultdict
    by_code = defaultdict(list)
    for r in rows:
        if r.get("value") is None:
            continue
        by_code[r["indicator_code"]].append((str(r["period"] or ""), float(r["value"])))
    trends = []
    for code, vals in by_code.items():
        vals.sort(key=lambda x: x[0])
        if len(vals) >= 2 and vals[-1][1]:
            chg = vals[-1][1] / vals[-2][1] - 1
            trends.append(_clamp(chg / 0.02 + 0.5))  # 环比 +2% → 1.0
    if not trends:
        return 0.5
    return sum(trends) / len(trends)


def _earnings_trend(symbol):
    """盈利趋势：营收/利润增速 → 0~1（>20% 增长 = 1, <-20% = 0）"""
    d = {f["metric"]: f["value"] for f in get_fundamentals(symbol)}
    scores = []
    for key in ("revenueGrowth", "epsGrowth"):
        v = d.get(key)
        if v is not None:
            scores.append(_clamp((float(v) + 0.2) / 0.4))
    if not scores:
        return 0.5
    return sum(scores) / len(scores)


def _price_trend(symbol):
    """价格趋势：收盘 vs MA20/MA60 + RSI 位置 → 0~1"""
    bars = get_prices(symbol, days=90)
    if len(bars) < 20:
        return 0.5
    closes = [float(b["close"]) for b in bars]
    last = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    score = 0.0
    score += 0.4 if last > ma20 else 0.0
    if ma60:
        score += 0.3 if last > ma60 else 0.0
    # RSI 位置（用 14 日简化）
    if len(closes) > 15:
        gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
        losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
        ag = sum(gains[-14:]) / 14
        al = sum(losses[-14:]) / 14
        rsi = 100.0 if al == 0 else 100 - 100 / (1 + ag / al) if al else 50
        score += 0.3 * _clamp(rsi / 100.0)
    return _clamp(score)


def _expectation_state(symbol):
    """市场预期强度：PE 与增速的背离（PEG 反向）
    PEG 低 = 预期不充分（0）；PEG 高 = 预期打满（1）"""
    d = {f["metric"]: f["value"] for f in get_fundamentals(symbol)}
    pe = d.get("pe")
    growth = d.get("revenueGrowth")
    if pe is None or growth is None or float(pe) <= 0:
        return 0.5
    peg = float(pe) / (float(growth) * 100) if float(growth) > 0 else 99
    return _clamp(peg / 3.0)  # PEG 0~3 → 0~1


def _macro_state():
    """宏观：FRED 序列（复用 regime 的宏观分）"""
    from context.regime_detector import _macro_score
    return _macro_score()


def build_context(symbol, persist=True, market_regime=None):
    """构建 Context Vector（含 Market Precondition）"""
    symbol = symbol.upper()
    # Market Precondition：优先传入，否则取库内最新 / 实时检测
    if market_regime is None:
        mr = get_latest_regime()
        market_regime = mr.get("regime_score")
    if market_regime is None:
        market_regime = 0.5

    vector = {
        "valuation": _valuation_state(symbol),
        "industry_cycle": _industry_cycle(symbol),
        "earnings_trend": _earnings_trend(symbol),
        "price_trend": _price_trend(symbol),
        "expectation": _expectation_state(symbol),
        "macro_regime": _macro_state(),
        "market_regime": float(market_regime),
    }
    confidence = _context_confidence(symbol, vector)
    result = {
        "symbol": symbol,
        "context_vector": {k: round(v, 4) for k, v in vector.items()},
        "confidence": round(confidence, 4),
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if persist:
        _save_context(symbol, vector, confidence)
    return result


def _context_confidence(symbol, vector):
    """Precondition 置信度：数据完整度 + 行情新鲜度"""
    filled = sum(1 for v in vector.values() if v is not None)
    base = filled / len(vector)
    price = get_latest_price(symbol)
    fresh = 1.0
    if price and price.get("timestamp"):
        age = (datetime.now() - price["timestamp"]).total_seconds()
        fresh = max(0.0, 1.0 - age / 86400)
    return base * (0.7 + 0.3 * fresh)


def _save_context(symbol, vector, confidence):
    import json
    stock = graph_repo.get_company(symbol=symbol)
    stock_id = None
    if stock:
        from data.repositories.mysql_db import get_stock
        s = get_stock(symbol)
        stock_id = s["id"] if s else None
    if stock_id is None:
        # 兜底：按 symbol 找 stock 行
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM stock WHERE symbol=%s", (symbol,))
            row = cur.fetchone()
            stock_id = row["id"] if row else None
    if stock_id is None:
        print(f"[precondition] stock 不存在，跳过持久化: {symbol}")
        return
    now = datetime.now().replace(microsecond=0)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO stock_precondition
                (stock_id, valuation, industry_cycle, earnings_trend, price_trend,
                 expectation, macro_regime, market_regime, confidence, detail, computed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              valuation=VALUES(valuation), industry_cycle=VALUES(industry_cycle),
              earnings_trend=VALUES(earnings_trend), price_trend=VALUES(price_trend),
              expectation=VALUES(expectation), macro_regime=VALUES(macro_regime),
              market_regime=VALUES(market_regime), confidence=VALUES(confidence),
              detail=VALUES(detail)
        """, (stock_id, vector["valuation"], vector["industry_cycle"],
              vector["earnings_trend"], vector["price_trend"],
              vector["expectation"], vector["macro_regime"], vector["market_regime"],
              confidence, json.dumps(vector, ensure_ascii=False), now))


def get_context(symbol, limit=1):
    """读取已保存的 Context Vector 历史"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT sp.*, st.symbol FROM stock_precondition sp
            JOIN stock st ON st.id = sp.stock_id
            WHERE st.symbol=%s ORDER BY sp.computed_at DESC LIMIT %s
        """, (symbol.upper(), limit))
        rows = cur.fetchall()
    import json
    for r in rows:
        if isinstance(r.get("detail"), str):
            try:
                r["detail"] = json.loads(r["detail"])
            except Exception:
                pass
    return rows


if __name__ == "__main__":
    import json
    print(json.dumps(build_context("NVDA"), ensure_ascii=False, indent=1, default=str))
