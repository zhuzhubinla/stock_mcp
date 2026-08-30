"""History Replay：历史时点重放，为 Phase 8 校准生成带真实 forward return 的样本

背景：在线学习需要 (成分分, 未来收益) 样本。新快照要等 5/20 天后才有收益，
为让校准闭环立即可验证，用历史价格在多个历史时点重放评分：
  - 每个时点只用该时点及之前的数据（避免 look-ahead bias）
  - 成分分：技术面（该时点之前）→ market/price；基本面/新闻用最近值近似
  - snapshot_time 设为历史时点 → backfill 后即有真实 forward return

注意：重放快照 weight_version='history-replay'，与真实快照区分。
"""
import sys
import json
from datetime import datetime, timedelta

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn, get_stock, get_prices
from scoring.score_engine import direction_of
from signals.confidence import compute_confidence

REPLAY_VERSION = "history-replay"
STEP_DAYS = 10      # 每隔 10 天取一个时点
MIN_BARS = 40       # 至少需要 40 根 bar 才能算技术指标


def _technical_score_at(bars, end_idx):
    """用 bars[:end_idx+1] 计算技术面分数（0~100）
    只用 end_idx 及之前的数据 → 无 look-ahead。
    """
    if end_idx + 1 < 20:
        return 50.0
    closes = [float(b["close"]) for b in bars[:end_idx + 1]]
    last = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    # 动量（10 日）
    mom = (last / closes[-11] - 1) if len(closes) > 11 else 0
    score = 50.0
    score += 15 if last > ma20 else -15
    if ma60:
        score += 10 if last > ma60 else -10
    score += max(-15, min(15, mom * 300))
    return max(0.0, min(100.0, score))


def _fundamental_approx(symbol):
    """基本面近似分：从当前 fundamentals 映射（重放期近似，标注说明）"""
    from data.repositories import mysql_db as db
    d = {f["metric"]: f["value"] for f in db.get_fundamentals(symbol)}
    score = 50.0
    if d.get("revenueGrowth") is not None:
        g = float(d["revenueGrowth"]) / 100
        score += max(-20, min(20, g * 30))
    if d.get("netMargin") is not None:
        m = float(d["netMargin"]) / 100
        score += max(-10, min(10, (m - 0.15) * 40))
    pe = d.get("pe")
    if pe is not None and float(pe) > 0:
        p = float(pe)
        score += 8 if p < 20 else (-8 if p > 50 else 0)
    return max(0.0, min(100.0, score))


def replay_symbol(symbol, days=120, step_days=STEP_DAYS, persist=True):
    """对单只股票生成历史重放快照，返回生成的时点数"""
    symbol = symbol.upper()
    stock = get_stock(symbol)
    if not stock:
        return {"symbol": symbol, "error": "stock 不存在"}
    bars = get_prices(symbol, days=days + 30)
    if len(bars) < MIN_BARS:
        return {"symbol": symbol, "error": f"历史数据不足: {len(bars)}"}

    stock_id = stock["id"]
    fund_score = _fundamental_approx(symbol)
    news_score = 50.0  # 新闻无法历史重放，中性
    pred_score = 50.0
    n_replayed = 0

    # 时点：从第 MIN_BARS 根开始，每隔 step_days 天一个
    for end_idx in range(MIN_BARS, len(bars), step_days):
        ts = bars[end_idx]["timestamp"]
        if ts.date() >= datetime.now().date():
            break  # 不要重放到今天（避免与真实快照混淆/未来收益不存在）
        tech = _technical_score_at(bars, end_idx)
        # 基本面随时间衰减：越早的时点越不精确，权重降低
        age_days = (datetime.now() - ts).total_seconds() / 86400
        decay = max(0.3, 1.0 - age_days / 365.0)
        market_score = 0.5 * tech + 0.5 * (fund_score * decay + 50 * (1 - decay))
        component_scores = {
            "fundamental": round(fund_score * decay + 50 * (1 - decay), 2),
            "precondition": round(market_score, 2),
            "market": round(tech, 2),
            "news": news_score,
            "prediction": pred_score,
        }
        total = sum(component_scores.values()) / len(component_scores)
        confidence, _ = compute_confidence(
            sources=["history-replay"], signals=[tech - 50, fund_score - 50],
            ages_hours=[0], n_samples=5, model_version=REPLAY_VERSION)
        if persist:
            _insert_replay_snapshot(stock_id, total, confidence, component_scores, ts)
        n_replayed += 1

    return {"symbol": symbol, "replayed": n_replayed,
            "bars_used": len(bars), "fund_approx": fund_score}


def _insert_replay_snapshot(stock_id, total, confidence, comps, ts):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO score_snapshot (stock_id, score, confidence, direction,
                                        weight_version, snapshot_time)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (stock_id, round(total, 2), confidence, direction_of(total),
              REPLAY_VERSION, ts.replace(second=0, microsecond=0)))
        sid = cur.lastrowid
        for c, v in comps.items():
            cur.execute("""
                INSERT INTO score_component (snapshot_id, component, score, weight, contribution)
                VALUES (%s, %s, %s, 0.2, %s)
            """, (sid, c, v, round(v * 0.2, 2)))


def replay_watchlist(symbols=None, persist=True):
    """对 watchlist 全部股票生成历史重放样本"""
    import json
    if symbols is None:
        try:
            symbols = json.load(open("/home/admin/stock_agent/watchlist.json"))
        except Exception:
            symbols = []
    results = []
    for s in symbols:
        try:
            results.append(replay_symbol(s, persist=persist))
        except Exception as e:
            results.append({"symbol": s, "error": str(e)})
    ok = sum(1 for r in results if r.get("replayed", 0) > 0)
    total = sum(r.get("replayed", 0) for r in results)
    print(f"[replay] {ok}/{len(results)} 股票重放成功, 共 {total} 个历史快照")
    return {"results": results, "total_snapshots": total}


if __name__ == "__main__":
    replay_watchlist(persist=True)
