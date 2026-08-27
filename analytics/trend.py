"""技术指标计算：基于历史 OHLCV 数据"""
import sys
sys.path.append("/home/admin/stock_agent")


def compute_indicators(prices):
    """prices: list of dicts with open/high/low/close/volume, 升序"""
    if not prices:
        return {}
    closes = [float(p["close"]) for p in prices]
    highs = [float(p["high"]) for p in prices]
    lows = [float(p["low"]) for p in prices]
    volumes = [float(p["volume"] or 0) for p in prices]
    n = len(closes)

    def sma(values, window):
        if len(values) < window:
            return None
        return sum(values[-window:]) / window

    def ema(values, window):
        if len(values) < window:
            return None
        k = 2 / (window + 1)
        e = sum(values[:window]) / window
        for v in values[window:]:
            e = v * k + e * (1 - k)
        return e

    # RSI(14)
    rsi = None
    if n > 14:
        gains, losses = [], []
        for i in range(1, n):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - 100 / (1 + rs)

    # MACD(12,26,9)
    macd = None
    macd_signal = None
    if n >= 26:
        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        if ema12 is not None and ema26 is not None:
            macd = ema12 - ema26

    # 均线
    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)

    # 波动率（20 日年化）
    volatility = None
    if n >= 21:
        rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, n)]
        mean = sum(rets[-20:]) / 20
        var = sum((r - mean) ** 2 for r in rets[-20:]) / 20
        volatility = (var ** 0.5) * (252 ** 0.5) * 100

    # 成交量比（最新 / 20日均量）
    volume_ratio = None
    if n >= 21:
        avg_vol = sum(volumes[-21:-1]) / 20
        if avg_vol > 0:
            volume_ratio = volumes[-1] / avg_vol

    # 涨跌幅
    change_pct = None
    if n >= 2 and closes[-2] != 0:
        change_pct = (closes[-1] / closes[-2] - 1) * 100

    # 52周高低（用现有数据近似）
    high_52w = max(highs)
    low_52w = min(lows)
    pos_from_low = None
    if high_52w - low_52w > 0:
        pos_from_low = (closes[-1] - low_52w) / (high_52w - low_52w) * 100

    return {
        "last_close": closes[-1],
        "change_pct": change_pct,
        "rsi14": rsi,
        "macd": macd,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "volatility_20d": volatility,
        "volume_ratio": volume_ratio,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pos_from_low_pct": pos_from_low,
        "samples": n,
    }


def summarize_technical(ind):
    """把指标转成简要文字描述"""
    if not ind:
        return "数据不足"
    parts = []
    if ind.get("rsi14") is not None:
        rsi = ind["rsi14"]
        if rsi >= 70:
            parts.append(f"RSI={rsi:.0f} 超买")
        elif rsi <= 30:
            parts.append(f"RSI={rsi:.0f} 超卖")
        else:
            parts.append(f"RSI={rsi:.0f} 中性")
    if ind.get("macd") is not None:
        parts.append(f"MACD={'正' if ind['macd'] > 0 else '负'} ({ind['macd']:.2f})")
    if ind.get("ma20") and ind.get("last_close"):
        trend = "多头" if ind["last_close"] > ind["ma20"] else "空头"
        parts.append(f"MA20趋势:{trend}")
    if ind.get("volume_ratio"):
        parts.append(f"量比={ind['volume_ratio']:.1f}")
    return "; ".join(parts)
