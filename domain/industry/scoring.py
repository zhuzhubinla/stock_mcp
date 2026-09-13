"""IndustryScorer（设计文档 §15.3 + industry/scoring.py）

汇总多因子 → 行业 score/direction/expected_return/confidence → 落 industry_macro_score。
"""
import sys
import json
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories import macro_repo
from domain.macro.factor import HORIZONS, MODEL_VERSION
from domain.macro.signal import compute_factor_signals
from domain.macro.regime import detect_macro_regime
from domain.industry.transmission import compute_impacts


def refresh_macro_scores(horizons=("1d", "1w", "1m"), persist=True,
                         regime_override=None, event_key=None, event_level="normal",
                         signals_override=None, signals=None):
    """完整刷新：信号 → regime → 各 horizon 行业分 → 落库。
    signals_override: {factor_code: value} 手动改信号（情景/事件日）。
    返回 {regime, regime_confidence, computed_at, horizons: {h: [行业行]}}"""
    if signals is None:
        signals = compute_factor_signals(persist=persist)
    if signals_override:
        signals.update({k: float(v) for k, v in signals_override.items()})
    # 图传播会激活 FED_POLICY 等传导因子，无需人工补
    sig_out = {k: v["signal"] if isinstance(v, dict) else v
               for k, v in signals.items()}

    if regime_override:
        regime_info = {"regime": regime_override, "confidence": 0.6}
    else:
        regime_info = detect_macro_regime(persist=persist)
    regime = regime_info["regime"]

    ts = datetime.now().replace(second=0, microsecond=0)
    result = {"regime": regime, "regime_confidence": regime_info["confidence"],
              "computed_at": str(ts), "horizons": {}}
    for hz in horizons:
        impacts = compute_impacts(sig_out, regime=regime, horizon=hz,
                                  event_key=event_key, event_level=event_level)
        if persist:
            for im in impacts:
                macro_repo.upsert_industry_macro_score(
                    im["industry_id"], hz, regime, im["score"],
                    im["expected_return_pct"], im["confidence"],
                    model_version=MODEL_VERSION, detail=im["drivers"],
                    score_date=ts)
        result["horizons"][hz] = impacts
    return result


def save_scenario_transmission(factor_changes, regime="neutral", horizon="1w",
                               event_key=None, event_level="normal",
                               event_id=None, event_source="scenario"):
    """情景模拟：信号覆盖 → 行业影响 → 落 industry_transmission_event（可追溯）"""
    from domain.macro.signal import latest_signals_dict
    signals = latest_signals_dict()
    base = {k: v["signal"] for k, v in signals.items()}
    base.update({k: float(v) for k, v in factor_changes.items()})
    impacts = compute_impacts(base, regime=regime, horizon=horizon,
                              event_key=event_key, event_level=event_level)
    if event_id is None:
        event_id = int(datetime.now().timestamp())
    for im in impacts:
        macro_repo.save_transmission_event(
            event_id=event_id, industry_id=im["industry_id"],
            impact_score=im["score"],
            direction=1.0 if im["direction"] == "bullish" else
                      (-1.0 if im["direction"] == "bearish" else 0.0),
            confidence=im["confidence"],
            explanation=json.dumps({"drivers": im["drivers"],
                                    "regime": regime, "horizon": horizon},
                                   ensure_ascii=False),
            event_source=event_source)
    return {"event_id": event_id, "event_source": event_source,
            "regime": regime, "horizon": horizon,
            "industries": [{k: im[k] for k in
                            ("industry_code", "industry_name", "score",
                             "direction", "confidence", "expected_return_pct")}
                           for im in impacts]}
