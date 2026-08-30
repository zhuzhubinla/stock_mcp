"""Score Engine（设计文档第 14 节 Overall Score）

OverallScore = Σ(ComponentScore_i × DynamicWeight_i)
标准化到 0-100：
  50 = Neutral / >70 = Bullish / >80 = Strong Bullish
  <30 = Bearish / <20 = Strong Bearish

同时持久化：
  - score_snapshot（总分/置信度/方向/权重版本/时间，回测基础）
  - score_component（成分分/权重/贡献拆解）
"""
import sys
import json
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_conn, get_stock
from scoring.weight_engine import select_weights, COMPONENTS, DEFAULT_WEIGHTS
from signals.confidence import compute_confidence


def _clamp(v, lo=0.0, hi=100.0):
    if v is None:
        return 50.0
    return max(lo, min(hi, float(v)))


def direction_of(score):
    if score >= 80:
        return "STRONG_BULLISH"
    if score >= 70:
        return "BULLISH"
    if score <= 20:
        return "STRONG_BEARISH"
    if score <= 30:
        return "BEARISH"
    return "NEUTRAL"


def compute_score(component_scores, context_vector=None, upcoming_event=None,
                  sources=None, signals=None, ages_hours=None, n_samples=None,
                  model_version="intelligence-v1"):
    """计算 Overall Score + 置信度 + 方向

    component_scores: {"fundamental": 0~100, "precondition": ..., "market": ...,
                       "news": ..., "prediction": ...}
    """
    weights, weight_version = select_weights(context_vector, upcoming_event)

    total = 0.0
    breakdown = []
    for c in COMPONENTS:
        raw = component_scores.get(c)
        # Precondition 成分分：把 context vector 转成 0~100 的"环境友好度"
        if c == "precondition" and raw is None and context_vector:
            raw = _precondition_score(context_vector)
        score = _clamp(raw) if raw is not None else 50.0
        w = weights.get(c, DEFAULT_WEIGHTS[c])
        contribution = score * w
        total += contribution
        breakdown.append({
            "component": c, "score": round(score, 2),
            "weight": round(w, 4), "contribution": round(contribution, 2),
        })

    confidence, conf_factors = compute_confidence(
        sources=sources, signals=signals, ages_hours=ages_hours,
        n_samples=n_samples, model_version=model_version)

    result = {
        "overall_score": round(total, 2),
        "confidence": confidence,
        "direction": direction_of(total),
        "weight_version": weight_version,
        "components": breakdown,
        "confidence_factors": conf_factors,
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return result


def _precondition_score(context_vector):
    """Context Vector → 0~100 环境友好度：
    低估值/低预期/趋势向上/risk-on → 高分（利好环境）
    高估值/高预期/risk_off → 低分（逆风环境）
    """
    v = context_vector
    # 估值高 = 环境差（反向）
    valuation = 1.0 - v.get("valuation", 0.5)
    expectation = 1.0 - v.get("expectation", 0.5)  # 预期打满 = 差
    price = v.get("price_trend", 0.5)
    market = v.get("market_regime", 0.5)
    macro = v.get("macro_regime", 0.5)
    industry = v.get("industry_cycle", 0.5)
    earnings = v.get("earnings_trend", 0.5)
    score = (0.2 * valuation + 0.15 * expectation + 0.2 * price
             + 0.2 * market + 0.1 * macro + 0.1 * industry + 0.05 * earnings)
    return _clamp(score * 100)


def save_snapshot(symbol, score_result):
    """持久化 score_snapshot + score_component"""
    stock = get_stock(symbol.upper())
    if not stock:
        print(f"[score] stock 不存在，跳过快照: {symbol}")
        return None
    stock_id = stock["id"]
    now = datetime.now().replace(second=0, microsecond=0)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO score_snapshot (stock_id, score, confidence, direction,
                                        weight_version, snapshot_time)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (stock_id, score_result["overall_score"], score_result["confidence"],
              score_result["direction"], score_result["weight_version"], now))
        snapshot_id = cur.lastrowid
        for c in score_result["components"]:
            cur.execute("""
                INSERT INTO score_component (snapshot_id, component, score, weight, contribution)
                VALUES (%s, %s, %s, %s, %s)
            """, (snapshot_id, c["component"], c["score"], c["weight"], c["contribution"]))
    return snapshot_id


def get_snapshot_history(symbol, limit=30):
    """评分历史（含成分拆解）"""
    stock = get_stock(symbol.upper())
    if not stock:
        return []
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id, score, confidence, direction, weight_version, snapshot_time,
                   forward_return_5d, forward_return_20d
            FROM score_snapshot WHERE stock_id=%s
            ORDER BY snapshot_time DESC LIMIT %s
        """, (stock["id"], limit))
        rows = cur.fetchall()
        for r in rows:
            cur.execute("""
                SELECT component, score, weight, contribution FROM score_component
                WHERE snapshot_id=%s
            """, (r["id"],))
            r["components"] = cur.fetchall()
    return rows


if __name__ == "__main__":
    scores = {"fundamental": 85, "market": 40, "news": 70, "prediction": 55}
    ctx = {"valuation": 0.82, "expectation": 0.9, "price_trend": 0.6,
           "market_regime": 0.7, "macro_regime": 0.6,
           "industry_cycle": 0.7, "earnings_trend": 0.8}
    r = compute_score(scores, context_vector=ctx)
    print(json.dumps(r, ensure_ascii=False, indent=1))
