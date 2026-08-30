"""Signal Engine：把原始数据转化为可解释的机器信号分数"""
import sys
sys.path.append("/home/admin/stock_agent")


def _clamp(v, lo=-100, hi=100):
    return max(lo, min(hi, v))


def price_signal(quote, ind):
    """价格信号：当日涨跌幅 + 位置"""
    score = 0.0
    desc = []
    chg = quote.get("percent") if quote else None
    if chg is None and ind:
        chg = ind.get("change_pct")
    if chg is not None:
        score += _clamp(chg * 2.5)          # 涨1% ≈ +2.5
        desc.append(f"当日涨跌 {chg:+.2f}%")
    if ind and ind.get("pos_from_low_pct") is not None:
        pos = ind["pos_from_low_pct"]
        if pos > 80:
            score += 10
            desc.append("接近52周高位")
        elif pos < 20:
            score -= 10
            desc.append("接近52周低位")
    return _clamp(score), "; ".join(desc)


def volume_signal(ind):
    """成交量信号：量比"""
    if not ind or not ind.get("volume_ratio"):
        return 0.0, ""
    vr = ind["volume_ratio"]
    if vr >= 2.0:
        return 15.0, f"放量 (量比{vr:.1f})"
    if vr >= 1.5:
        return 8.0, f"温和放量 (量比{vr:.1f})"
    if vr <= 0.5:
        return -8.0, f"缩量 (量比{vr:.1f})"
    return 0.0, f"量比{vr:.1f}"


def technical_signal(ind):
    """技术信号：RSI + 均线趋势 + MACD"""
    score = 0.0
    desc = []
    if not ind:
        return 0.0, "数据不足"
    rsi = ind.get("rsi14")
    if rsi is not None:
        if rsi >= 70:
            score -= 12
            desc.append(f"RSI={rsi:.0f} 超买")
        elif rsi <= 30:
            score += 12
            desc.append(f"RSI={rsi:.0f} 超卖(反弹潜力)")
        elif 45 <= rsi <= 60:
            score += 5
            desc.append(f"RSI={rsi:.0f} 健康")
    close = ind.get("last_close")
    ma20 = ind.get("ma20")
    ma60 = ind.get("ma60")
    if close and ma20 and ma60:
        if close > ma20 > ma60:
            score += 12
            desc.append("多头排列")
        elif close < ma20 < ma60:
            score -= 12
            desc.append("空头排列")
        elif close > ma20:
            score += 5
            desc.append("站上MA20")
        else:
            score -= 5
            desc.append("跌破MA20")
    macd = ind.get("macd")
    if macd is not None:
        score += 6 if macd > 0 else -6
        desc.append(f"MACD{'金叉区' if macd > 0 else '死叉区'}")
    return _clamp(score), "; ".join(desc)


def news_signal(news_list):
    """新闻信号：基于简单关键词情感打分"""
    if not news_list:
        return 0.0, "无近期新闻"
    pos_words = ["beat", "surge", "record", "growth", "upgrade", "outperform",
                 "win", "positive", "profit", "rally", "strong", "jump", "gain"]
    neg_words = ["miss", "plunge", "downgrade", "lawsuit", "investigation",
                 "weak", "loss", "cut", "decline", "fall", "recall", "ban", "risk"]
    score = 0.0
    hits = []
    for n in news_list[:5]:
        title = (n.get("title") or "")
        low = title.lower()
        s = 0
        for w in pos_words:
            if w in low:
                s += 2
        for w in neg_words:
            if w in low:
                s -= 2
        if s != 0:
            score += _clamp(s, -6, 6)
            hits.append(f"{title[:40]}({s:+d})")
    if not hits:
        return 0.0, "新闻无明确方向"
    return _clamp(score), "; ".join(hits[:3])


def fundamental_signal(fundamentals):
    """基本面信号：利润率、营收增长等"""
    if not fundamentals:
        return 0.0, "无基本面数据"
    d = {f["metric"]: f["value"] for f in fundamentals}
    score = 0.0
    desc = []
    for key, good in [("grossMargin", True), ("netMargin", True), ("roe", True)]:
        v = d.get(key)
        if v is not None:
            if good and v > 0:
                score += 6
                desc.append(f"{key}={v:.1%}")
            elif v < 0:
                score -= 6
                desc.append(f"{key}={v:.1%}")
    for key in ["revenueGrowth", "epsGrowth"]:
        v = d.get(key)
        if v is not None:
            if v > 0.1:
                score += 8
                desc.append(f"{key}={v:.1%}")
            elif v < 0:
                score -= 8
                desc.append(f"{key}={v:.1%}")
    pe = d.get("pe")
    if pe is not None:
        if 0 < pe < 25:
            score += 5
            desc.append(f"PE={pe:.1f}")
        elif pe >= 50:
            score -= 8
            desc.append(f"PE={pe:.1f} 偏贵")
    return _clamp(score), "; ".join(desc)


def market_signal(quote):
    """市场情绪信号：基于涨跌幅的简单代理"""
    if not quote:
        return 0.0, ""
    chg = quote.get("percent")
    if chg is None:
        return 0.0, ""
    if chg > 3:
        return 12.0, "强势上涨"
    if chg < -3:
        return -12.0, "明显下跌"
    return 0.0, ""


def compute_total(quote, ind, news_list, fundamentals):
    """汇总 6 类信号，返回总分和明细"""
    ps, pd_ = price_signal(quote, ind)
    vs, vd = volume_signal(ind)
    ts, td = technical_signal(ind)
    ns, nd = news_signal(news_list)
    fs, fd = fundamental_signal(fundamentals)
    ms, md = market_signal(quote)

    total = _clamp(ps + vs + ts + ns + fs + ms, -100, 100)

    components = [
        {"name": "Price Signal", "score": round(ps, 1), "desc": pd_},
        {"name": "Volume Signal", "score": round(vs, 1), "desc": vd},
        {"name": "Technical Signal", "score": round(ts, 1), "desc": td},
        {"name": "News Signal", "score": round(ns, 1), "desc": nd},
        {"name": "Fundamental Signal", "score": round(fs, 1), "desc": fd},
        {"name": "Market Signal", "score": round(ms, 1), "desc": md},
    ]
    if total >= 30:
        level = "偏多"
    elif total <= -30:
        level = "偏空"
    else:
        level = "中性"
    return {
        "total_score": round(total, 1),
        "level": level,
        "components": components,
    }


if __name__ == "__main__":
    # 冒烟测试
    q = {"percent": 2.5}
    ind = {"rsi14": 55,
           "last_close": 120,
           "ma20": 115,
           "ma60": 110,
           "macd": 0.8,
           "volume_ratio": 1.8,
           "pos_from_low_pct": 85}
    news = [{"title": "Company beats earnings, stock surges"}]
    fund = [{"metric": "netMargin", "value": 0.25},
            {"metric": "revenueGrowth", "value": 0.15}]
    r = compute_total(q, ind, news, fund)
    print(r)
