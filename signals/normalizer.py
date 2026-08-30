"""Signal Normalizer：把各域原始信号统一标准化到 [-1, +1]（设计文档第 9 节）"""
import sys
sys.path.append("/home/admin/stock_agent")


def _clamp(v, lo=-1.0, hi=1.0):
    if v is None:
        return 0.0
    return max(lo, min(hi, float(v)))


def normalize_price(chg_pct):
    """涨跌幅 → [-1,1]：±5% 封顶线性"""
    if chg_pct is None:
        return 0.0
    return _clamp(float(chg_pct) / 5.0)


def normalize_rsi(rsi, neutral_lo=45, neutral_hi=60):
    """RSI → [-1,1]：超卖(<=30)=+1（反弹潜力），超买(>=70)=-1，中性=0"""
    if rsi is None:
        return 0.0
    rsi = float(rsi)
    if rsi <= 30:
        return 1.0
    if rsi >= 70:
        return -1.0
    if neutral_lo <= rsi <= neutral_hi:
        return 0.0
    if rsi < neutral_lo:
        return _clamp((neutral_lo - rsi) / 15.0)
    return _clamp((neutral_hi - rsi) / 10.0)


def normalize_trend(close, ma20, ma60):
    """均线排列 → [-1,1]：多头排列 +1，空头 -1，站上 MA20 +0.4"""
    if close is None or ma20 is None:
        return 0.0
    if ma60 is not None and close > ma20 > ma60:
        return 1.0
    if ma60 is not None and close < ma20 < ma60:
        return -1.0
    return 0.4 if close > ma20 else -0.4


def normalize_sentiment(sentiment_score):
    """新闻情感分（-1~1）→ [-1,1]，原样截断"""
    return _clamp(sentiment_score)


def normalize_growth(growth):
    """增速 → [-1,1]：+20% = +1，-20% = -1"""
    if growth is None:
        return 0.0
    return _clamp(float(growth) / 0.2)


def normalize_probability(prob, anchor=0.5):
    """预测市场概率 → [-1,1]：概率相对锚点（默认 50%）的偏离"""
    if prob is None:
        return 0.0
    return _clamp((float(prob) - anchor) / 0.5)


def normalize_component(score, lo=0.0, hi=100.0):
    """0~100 成分分 → [-1,1]"""
    if score is None:
        return 0.0
    return _clamp((float(score) - (lo + hi) / 2) / ((hi - lo) / 2))


if __name__ == "__main__":
    print("price +2.5%:", normalize_price(2.5))
    print("rsi 25:", normalize_rsi(25), "| rsi 75:", normalize_rsi(75))
    print("trend:", normalize_trend(120, 115, 110))
    print("sentiment 0.3:", normalize_sentiment(0.3))
    print("growth 15%:", normalize_growth(0.15))
    print("prob 0.7:", normalize_probability(0.7))
