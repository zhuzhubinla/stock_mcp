"""Industry Transmission use cases：Phase 7 MCP 层编排（对齐 app/use_cases 风格）
覆盖设计文档 §18 API：macro-score / transmission / exposure / simulate
"""
import sys

sys.path.append("/home/admin/stock_agent")

from data.repositories import macro_repo, graph_repo
from domain.industry.scoring import refresh_macro_scores, save_scenario_transmission
from domain.industry.exposure import ExposureManager
from domain.macro.regime import detect_macro_regime
from domain.macro.factor import HORIZONS, MODEL_VERSION
from domain.macro.signal import compute_factor_signals, latest_signals_dict


def _industry_id(industry_code):
    if not industry_code:
        return None
    ind = graph_repo.get_industry(code=industry_code)
    return ind["id"] if ind else None


def macro_scores(industry_code=None, horizon=None, refresh=False, limit=50):
    """行业宏观分（最新快照；refresh=True 重新计算全行业全 horizon）"""
    meta = {}
    if refresh:
        res = refresh_macro_scores()
        meta = {"regime": res["regime"], "computed_at": res["computed_at"]}
    iid = _industry_id(industry_code)
    rows = macro_repo.get_latest_scores(industry_id=iid, horizon=horizon, limit=limit)
    out = []
    for r in rows:
        sc = float(r["score"])
        out.append({
            "industry": r["industry_code"], "industry_name": r["industry_name"],
            "horizon": r["horizon"], "score": sc,
            "direction": "bullish" if sc > 0.02 else ("bearish" if sc < -0.02 else "neutral"),
            "expected_return_pct": float(r["expected_return"] or 0),
            "confidence": float(r["confidence"]),
            "regime": r["regime"],
            "computed_at": str(r["score_date"]),
            "drivers": r.get("detail"),
        })
    return {"regime": meta.get("regime") or (rows[0]["regime"] if rows else None),
            "count": len(out), "scores": out}


def macro_regime(force_refresh=False):
    """当前宏观 regime（goldilocks/overheating/recession/stagflation/neutral）"""
    if force_refresh:
        info = detect_macro_regime(persist=True)
        return info
    row = macro_repo.get_latest_macro_regime()
    if not row:
        return detect_macro_regime(persist=True)
    return {"regime": row["regime"], "confidence": float(row["confidence"]),
            "growth_yoy": float(row["growth_yoy"]) if row["growth_yoy"] is not None else None,
            "inflation_yoy": float(row["inflation_yoy"]) if row["inflation_yoy"] is not None else None,
            "detail": row.get("detail"),
            "snapshot_time": str(row["snapshot_time"])}


def macro_exposures(industry_code=None, factor_code=None, horizon="1w"):
    """宏观因子→行业敏感性（EffectiveExposure，含当前 regime/event/horizon 修正）"""
    row = macro_repo.get_latest_macro_regime()
    regime = row["regime"] if row else "neutral"
    em = ExposureManager(regime=regime, horizon=horizon)
    iid = _industry_id(industry_code)
    rows = em.load_effective(industry_id=iid, factor_code=factor_code)
    return {"regime": regime, "horizon": horizon, "count": len(rows),
            "exposures": rows}


def macro_factors():
    """宏观因子主数据 + 最新信号"""
    sigs = latest_signals_dict()
    out = []
    for f in macro_repo.list_factors():
        s = sigs.get(f["code"], {})
        out.append({
            "factor": f["code"], "name": f["name"], "category": f["category"],
            "direction_note": f["direction_note"],
            "signal": s.get("signal"),
            "z_score": s.get("z"),
            "indicator_code": s.get("indicator_code"),
            "as_of": s.get("as_of"),
        })
    return {"count": len(out), "factors": out}


def simulate(factor_changes, event_key=None, event_level="normal",
             horizon="1w", event_id=None):
    """情景模拟：宏观因子信号假设 → 行业影响（落 industry_transmission_event）
    factor_changes: dict，如 {"RATES": -0.5} 或 {"FED_POLICY": 0.8}"""
    if not isinstance(factor_changes, dict) or not factor_changes:
        return {"error": "factor_changes 需为 {因子代码: 信号值}，如 {\"RATES\": -0.5}"}
    row = macro_repo.get_latest_macro_regime()
    regime = row["regime"] if row else "neutral"
    return save_scenario_transmission(
        factor_changes, regime=regime, horizon=horizon,
        event_key=event_key, event_level=event_level,
        event_id=event_id, event_source="scenario")


def transmission_events(event_id=None, industry_code=None, limit=20):
    """历史传导事件记录（真实数据日 vs 情景均可查）"""
    iid = _industry_id(industry_code)
    rows = macro_repo.get_transmission_events(event_id=event_id, industry_id=iid,
                                              limit=limit)
    return {"count": len(rows), "events": rows}
