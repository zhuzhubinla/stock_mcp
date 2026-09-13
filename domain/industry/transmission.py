"""Transmission Engine（设计文档 §7/§8/§16 + Python 架构 industry/transmission.py）

计算管线：
  Macro Signal → Transmission Graph 传播（Indirect）
  → Exposure（EffectiveExposure，含 Regime/Event/Horizon 修正）
  → Industry Impact = Σ FactorSignal × EffectiveExposure × Confidence
"""
import sys

sys.path.append("/home/admin/stock_agent")

from domain.industry.exposure import ExposureManager
from domain.industry.graph import TransmissionGraph
from domain.macro.factor import HORIZON_RETURN_SCALE


def _clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


def compute_impacts(signals, regime="neutral", horizon="1w", event_key=None,
                    event_level="normal", industries=None):
    """核心：宏观信号 → 各行业 impact。
    signals: {factor_code: value}；industries 为 None 时用全部有 exposure 的行业。
    返回 [{industry_id, industry_code, industry_name, score, direction, confidence,
           expected_return_pct, drivers:[...]}] 按 |score| 降序。"""
    # 1) 图传播（Indirect）
    graph = TransmissionGraph()
    propagated = graph.propagate(signals)

    # 2) Effective Exposure
    em = ExposureManager(regime=regime, horizon=horizon,
                         event_key=event_key, event_level=event_level)
    exposure_map = em.industry_exposure_map()
    detail_rows = em.load_effective()

    # industry 元数据
    meta = {}
    for r in detail_rows:
        meta[r["industry_id"]] = (r["industry_code"], r["industry_name"])

    # 3) 每行业聚合
    results = []
    for iid, factor_expo in exposure_map.items():
        if industries is not None and iid not in industries:
            continue
        contribs = []
        total = 0.0
        for fcode, eff in factor_expo.items():
            sig = propagated.get(fcode)
            if not sig or abs(sig["value"]) < 1e-6 or abs(eff) < 1e-6:
                continue
            contrib = sig["value"] * eff * sig["conf"]
            total += contrib
            contribs.append({
                "factor": fcode,
                "signal": round(sig["value"], 4),
                "effective_exposure": round(eff, 4),
                "contribution": round(contrib, 6),
                "path": sig.get("path", [fcode]),
            })
        if not contribs:
            continue
        code, name = meta.get(iid, (str(iid), str(iid)))
        score = _clamp(total)
        # 置信度：贡献集中度越高越可信（启发式，V1）
        abs_sum = sum(abs(c["contribution"]) for c in contribs)
        conf = _clamp(0.5 + 0.5 * abs_sum / (0.15 + abs_sum), 0.3, 0.95)
        direction = "bullish" if score > 0.02 else ("bearish" if score < -0.02 else "neutral")
        ret_scale = HORIZON_RETURN_SCALE.get(horizon, 2.0)
        results.append({
            "industry_id": iid,
            "industry_code": code,
            "industry_name": name,
            "regime": regime,
            "horizon": horizon,
            "score": round(score, 6),
            "direction": direction,
            "confidence": round(conf, 4),
            "expected_return_pct": round(score * ret_scale, 4),
            "drivers": sorted(contribs, key=lambda c: abs(c["contribution"]), reverse=True),
        })
    results.sort(key=lambda r: abs(r["score"]), reverse=True)
    return results
