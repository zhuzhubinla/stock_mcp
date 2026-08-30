"""Prediction 领域层：Consensus / Momentum / Signal（设计文档 8.4-8.6）

Consensus = Σ(P_i × W_i) / Σ(W_i)
  W_i = source reliability / liquidity / quality 权重
  同时计算 Source Dispersion（源间标准差）：一致→提 Confidence，差异大→降 Confidence

Momentum_24h = P_now - P_24h_ago；Momentum_7d = P_now - P_7d_ago

Prediction → Stock 映射必须经 Knowledge Graph（8.6 节）：
  预测事件本身不是股票信号，完成实体/产业链映射后才能进入 Stock Score。
"""
import sys
import math
from datetime import datetime, timedelta

sys.path.append("/home/admin/stock_agent")

from data.repositories import prediction_repo as repo


def compute_momentum(market_id, outcome_key="yes", hours_24=24, hours_7d=168):
    """概率动量：最新 vs N 小时前"""
    hist = repo.get_probability_history(market_id, outcome_key, hours=max(hours_24, hours_7d))
    if len(hist) < 2:
        return {"momentum_24h": None, "momentum_7d": None}
    latest = float(hist[-1]["probability"])
    now = datetime.now()
    m24 = m7d = None
    for r in hist:
        age = (now - r["observed_at"]).total_seconds() / 3600
        if m24 is None and age >= hours_24:
            m24 = latest - float(r["probability"])
        if m7d is None and age >= hours_7d:
            m7d = latest - float(r["probability"])
    # 样本不足时用最早一条近似
    if m24 is None:
        m24 = latest - float(hist[0]["probability"])
    if m7d is None:
        m7d = latest - float(hist[0]["probability"])
    return {"momentum_24h": round(m24, 4), "momentum_7d": round(m7d, 4)}


def compute_consensus(event_id, persist=True):
    """多源共识：同事件下所有市场的加权概率
    weight = source.weight × (0.5 + liquidity 因子)
    dispersion = 概率标准差
    """
    markets = _event_markets(event_id)
    if not markets:
        return None
    rows = []
    for m in markets:
        if m.get("last_price") is None:
            continue
        # 源权重（来自 prediction_source.weight）
        src = repo.get_source(m["source_code"])
        w_src = float(src["weight"]) if src else 1.0
        # 流动性因子：open_interest 高 → 权重高（0.5~1.5）
        oi = float(m.get("open_interest") or 0)
        w_liq = 0.5 + min(1.0, oi / 1000.0)
        rows.append({"market": m, "p": float(m["last_price"]), "w": w_src * w_liq})
    if not rows:
        return None
    total_w = sum(r["w"] for r in rows)
    prob = sum(r["p"] * r["w"] for r in rows) / total_w if total_w else None
    # dispersion：加权标准差
    dispersion = None
    if len(rows) > 1 and prob is not None:
        var = sum(r["w"] * (r["p"] - prob) ** 2 for r in rows) / total_w
        dispersion = math.sqrt(var)

    # momentum：取主市场
    main_m = max(rows, key=lambda r: r["w"])["market"]
    mom = compute_momentum(main_m["id"])

    result = {
        "event_id": event_id,
        "probability": round(prob, 4) if prob is not None else None,
        "dispersion": round(dispersion, 4) if dispersion is not None else None,
        "source_count": len(rows),
        "momentum_24h": mom["momentum_24h"],
        "momentum_7d": mom["momentum_7d"],
        "detail": {"markets": [{"market_id": r["market"]["id"],
                                "p": r["p"], "w": round(r["w"], 3),
                                "source": r["market"]["source_code"]} for r in rows]},
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if persist and prob is not None:
        repo.save_consensus(event_id, result["probability"], result["dispersion"],
                            result["source_count"], result["momentum_24h"],
                            result["momentum_7d"], result["detail"])
    return result


def _event_markets(event_id):
    """事件下的所有市场（含源信息）"""
    with repo.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT m.*, s.code AS source_code FROM prediction_market m
            JOIN prediction_source s ON s.id = m.source_id
            WHERE m.event_id=%s AND m.last_price IS NOT NULL
        """, (event_id,))
        return cur.fetchall()


def confidence_from_consensus(consensus):
    """共识 → 置信度：dispersion 低 + 源数多 → 高置信"""
    if not consensus or consensus.get("probability") is None:
        return 0.0
    disp = consensus.get("dispersion")
    n = consensus.get("source_count", 1)
    disp_factor = 1.0 if disp is None else max(0.0, 1.0 - disp * 4)
    n_factor = min(1.0, n / 3.0)
    return round(0.6 * disp_factor + 0.4 * n_factor, 4)


def direction_from_probability(prob, momentum=None):
    """概率+动量 → 方向与强度（-1~1）
    prob > 0.6 且动量正 → bullish；prob < 0.4 → bearish
    """
    if prob is None:
        return "neutral", 0.0
    strength = (prob - 0.5) * 2  # -1~1
    mom = momentum or 0
    if abs(mom) > 0.02:
        strength += mom * 3
    strength = max(-1.0, min(1.0, strength))
    if strength > 0.2:
        direction = "bullish"
    elif strength < -0.2:
        direction = "bearish"
    else:
        direction = "neutral"
    return direction, round(strength, 4)


def compute_all_consensus(persist=True, category=None):
    """为所有 open 事件计算共识（可选按类别）"""
    events = repo.list_events(status="open", category=category, limit=100)
    out = []
    for e in events:
        c = compute_consensus(e["id"], persist=persist)
        if c and c.get("probability") is not None:
            out.append({"event_id": e["id"], "title": e["title"],
                        "category": e["category"], **c})
    return out


if __name__ == "__main__":
    import json
    cs = compute_all_consensus(persist=True)
    print(f"consensus computed: {len(cs)}")
    for c in cs[:10]:
        print(f"  #{c['event_id']} [{c['category']}] p={c['probability']} "
              f"disp={c['dispersion']} mom24h={c['momentum_24h']} srcs={c['source_count']}")
