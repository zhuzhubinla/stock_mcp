"""价格异常检测 + 新闻事件归因（Price Anomaly + News Event -> Possible Cause）"""
from datetime import datetime, timedelta

from config import ANOMALY_NEWS_WINDOW_HOURS
from intelligence.repositories import mysql_db as db
from intelligence.services import stock_service

PRICE_THRESHOLD = 4.0    # |单日涨跌| >= 4%
VOLUME_THRESHOLD = 2.5   # 量比 >= 2.5


def detect(symbol, days=30):
    """扫描日线，返回异常日列表"""
    hist = stock_service.get_history(symbol, days=days)
    bars = hist.get("bars", [])
    anomalies = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1]["close"]
        if not prev_close:
            continue
        cur = bars[i]
        pct = (cur["close"] - prev_close) / prev_close * 100
        window = [b["volume"] for b in bars[max(0, i - 20):i] if b.get("volume")]
        avg_v = sum(window) / len(window) if window else 0
        vr = cur["volume"] / avg_v if avg_v else 0
        reasons = []
        if abs(pct) >= PRICE_THRESHOLD:
            reasons.append(f"涨跌{pct:+.1f}%")
        if vr >= VOLUME_THRESHOLD:
            reasons.append(f"量比{vr:.1f}")
        if reasons:
            anomalies.append({
                "date": cur["date"], "close": cur["close"],
                "change_pct": round(pct, 2), "volume_ratio": round(vr, 2),
                "direction": "up" if pct > 0 else "down", "reasons": reasons,
            })
    return anomalies


def get_anomalies_with_causes(symbol, days=30, window_hours=None):
    """异常日 + 窗口内高影响新闻事件"""
    window_hours = window_hours or ANOMALY_NEWS_WINDOW_HOURS
    anomalies = detect(symbol, days)
    half = window_hours // 2
    for a in anomalies:
        try:
            dt = datetime.strptime(a["date"], "%Y-%m-%d")
        except ValueError:
            a["causes"] = []
            continue
        start, end = dt - timedelta(hours=half), dt + timedelta(hours=half)
        news = [n for n in db.get_news_between(symbol, start, end, limit=10)
                if n.get("impact_score") is not None]
        news.sort(key=lambda n: float(n["impact_score"] or 0), reverse=True)
        a["causes"] = news[:5]
    return {"symbol": symbol, "days": days, "anomalies": anomalies, "count": len(anomalies)}


def explain_price_move(symbol, days=10):
    """解释最近一次异常波动：价格异常 + 新闻归因"""
    data = get_anomalies_with_causes(symbol, days=days)
    if not data["anomalies"]:
        return {"symbol": symbol, "explained": False,
                "message": f"近 {days} 个交易日未检测到显著异常（|涨跌|≥{PRICE_THRESHOLD}% 或 量比≥{VOLUME_THRESHOLD}）"}
    latest = data["anomalies"][-1]
    causes = [{
        "title": n["title"], "event_type": n.get("event_type"),
        "impact_score": float(n["impact_score"] or 0),
        "sentiment": n.get("sentiment"),
        "published_at": str(n["published_at"]),
    } for n in latest.get("causes", [])]
    if causes:
        top = "；".join(f"《{c['title'][:60]}》(影响度{c['impact_score']:.2f})" for c in causes[:3])
        explanation = (f"{symbol} 在 {latest['date']} 出现异常波动：{latest['reasons'][0]}，"
                       f"收于 {latest['close']}。可能的触发新闻：{top}。")
    else:
        explanation = (f"{symbol} 在 {latest['date']} 出现异常波动：{latest['reasons'][0]}，"
                       f"收于 {latest['close']}。窗口内未找到高影响新闻，可能为板块/宏观驱动。")
    return {"symbol": symbol, "explained": True,
            "anomaly": {k: latest[k] for k in
                        ("date", "close", "change_pct", "volume_ratio", "direction", "reasons")},
            "causes": causes, "explanation": explanation}
